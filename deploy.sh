#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
REGION="europe-north1"
SERVICE_NAME="blocket-monitor"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "Building container image..."
gcloud builds submit --tag "${IMAGE}" .

echo "Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --platform managed \
  --memory 512Mi \
  --timeout 300 \
  --max-instances 1 \
  --set-env-vars "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}" \
  --update-env-vars "RESEND_API_KEY=${RESEND_API_KEY}" \
  --update-env-vars "GRACE_GW_API_KEY=${GRACE_GW_API_KEY}" \
  --update-env-vars "TRIGGER_API_KEY=${TRIGGER_API_KEY}" \
  --update-env-vars "DATABASE_PATH=data/blocket.db" \
  --update-env-vars "EMAIL_RECIPIENTS=${EMAIL_RECIPIENTS}" \
  --update-env-vars "EMAIL_FROM=${EMAIL_FROM:-blocket@autostoresverige.com}" \
  --no-allow-unauthenticated

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" \
  --format "value(status.url)")

echo "Service deployed at: ${SERVICE_URL}"

echo "Creating Cloud Scheduler jobs..."
gcloud scheduler jobs delete "${SERVICE_NAME}-trigger" \
  --location "${REGION}" --quiet 2>/dev/null || true

gcloud scheduler jobs create http "${SERVICE_NAME}-trigger" \
  --location "${REGION}" \
  --schedule "0 6-23 * * *" \
  --time-zone "Europe/Stockholm" \
  --uri "${SERVICE_URL}/trigger" \
  --http-method POST \
  --headers "X-API-Key=${TRIGGER_API_KEY}" \
  --oidc-service-account-email "${PROJECT_ID}@appspot.gserviceaccount.com" \
  --oidc-token-audience "${SERVICE_URL}"

# Also schedule midnight run
gcloud scheduler jobs delete "${SERVICE_NAME}-trigger-midnight" \
  --location "${REGION}" --quiet 2>/dev/null || true

gcloud scheduler jobs create http "${SERVICE_NAME}-trigger-midnight" \
  --location "${REGION}" \
  --schedule "0 0 * * *" \
  --time-zone "Europe/Stockholm" \
  --uri "${SERVICE_URL}/trigger" \
  --http-method POST \
  --headers "X-API-Key=${TRIGGER_API_KEY}" \
  --oidc-service-account-email "${PROJECT_ID}@appspot.gserviceaccount.com" \
  --oidc-token-audience "${SERVICE_URL}"

echo "Done! Scheduler configured for hourly runs 06:00-00:00 Stockholm time."
