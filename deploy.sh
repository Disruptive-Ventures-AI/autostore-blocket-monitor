#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
REGION="europe-north1"
SERVICE_NAME="blocket-monitor"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "Building container image..."
gcloud builds submit --tag "${IMAGE}" .

echo "Deploying to Cloud Run..."

# Write env vars to a temp YAML file so secrets are not leaked in process args.
ENV_FILE=$(mktemp)
trap 'rm -f "${ENV_FILE}"' EXIT
cat > "${ENV_FILE}" <<ENVEOF
ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}"
RESEND_API_KEY: "${RESEND_API_KEY}"
GRACE_GW_API_KEY: "${GRACE_GW_API_KEY}"
TRIGGER_API_KEY: "${TRIGGER_API_KEY}"
DATABASE_PATH: "data/blocket.db"
EMAIL_RECIPIENTS: "${EMAIL_RECIPIENTS}"
EMAIL_FROM: "${EMAIL_FROM:-blocket@autostoresverige.com}"
ENVEOF
chmod 600 "${ENV_FILE}"

gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --memory 512Mi \
  --timeout 300 \
  --max-instances 1 \
  --env-vars-file "${ENV_FILE}" \
  --no-allow-unauthenticated

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" \
  --format "value(status.url)")

echo "Service deployed at: ${SERVICE_URL}"

echo "Creating Cloud Scheduler jobs..."

# Use --flags-file to pass scheduler config including the API key header,
# so secrets are not exposed in process arguments visible via ps/proc.
create_scheduler_job() {
  local job_name="$1" schedule="$2"
  local flags_file
  flags_file=$(mktemp)
  cat > "${flags_file}" <<FLAGSEOF
--location: "${REGION}"
--schedule: "${schedule}"
--time-zone: "Europe/Stockholm"
--uri: "${SERVICE_URL}/trigger"
--http-method: POST
--headers: "X-API-Key=${TRIGGER_API_KEY}"
--oidc-service-account-email: "${PROJECT_ID}@appspot.gserviceaccount.com"
--oidc-token-audience: "${SERVICE_URL}"
FLAGSEOF
  chmod 600 "${flags_file}"
  gcloud scheduler jobs delete "${job_name}" \
    --location "${REGION}" --quiet 2>/dev/null || true
  gcloud scheduler jobs create http "${job_name}" --flags-file="${flags_file}"
  rm -f "${flags_file}"
}

create_scheduler_job "${SERVICE_NAME}-trigger" "0 6-23 * * *"
# Also schedule midnight run
create_scheduler_job "${SERVICE_NAME}-trigger-midnight" "0 0 * * *"

echo "Done! Scheduler configured for hourly runs 06:00-00:00 Stockholm time."
