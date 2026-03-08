#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-dv-orchestrator}"
REGION="europe-north1"
SERVICE_NAME="blocket-monitor"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"
BUCKET="blocket-monitor-data"
SA="152318493064-compute@developer.gserviceaccount.com"

echo "Building container image..."
gcloud builds submit --tag "${IMAGE}" --project "${PROJECT_ID}" .

echo "Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --project "${PROJECT_ID}" \
  --platform managed \
  --execution-environment gen2 \
  --memory 512Mi \
  --timeout 300 \
  --max-instances 1 \
  --min-instances 0 \
  --service-account "${SA}" \
  --set-secrets="ANTHROPIC_API_KEY=orchestrator-anthropic-key:latest,RESEND_API_KEY=orchestrator-resend-key:latest,GRACE_GW_API_KEY=orchestrator-grace-gw-key:latest,TRIGGER_API_KEY=orchestrator-trigger-key:latest" \
  --set-env-vars="^##^DATABASE_PATH=/data/blocket.db##EMAIL_RECIPIENTS=erik+blocket@autostoresverige.com,serge+autostore@lachapelle.se##EMAIL_FROM=blocket@autostoresverige.com" \
  --add-volume=name=data-vol,type=cloud-storage,bucket=${BUCKET} \
  --add-volume-mount=volume=data-vol,mount-path=/data \
  --no-allow-unauthenticated

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --region "${REGION}" --project "${PROJECT_ID}" \
  --format "value(status.url)")

echo "Service deployed at: ${SERVICE_URL}"

echo "Setting up Cloud Scheduler..."
# Delete existing jobs if any
gcloud scheduler jobs delete "${SERVICE_NAME}-hourly" \
  --location "${REGION}" --project "${PROJECT_ID}" --quiet 2>/dev/null || true
gcloud scheduler jobs delete "${SERVICE_NAME}-midnight" \
  --location "${REGION}" --project "${PROJECT_ID}" --quiet 2>/dev/null || true

# Hourly 06:00-23:00
gcloud scheduler jobs create http "${SERVICE_NAME}-hourly" \
  --location "${REGION}" --project "${PROJECT_ID}" \
  --schedule "0 6-23 * * *" \
  --time-zone "Europe/Stockholm" \
  --uri "${SERVICE_URL}/trigger" \
  --http-method POST \
  --headers "X-API-Key=$(gcloud secrets versions access latest --secret=orchestrator-trigger-key --project=${PROJECT_ID})" \
  --oidc-service-account-email "${SA}" \
  --oidc-token-audience "${SERVICE_URL}"

# Midnight run
gcloud scheduler jobs create http "${SERVICE_NAME}-midnight" \
  --location "${REGION}" --project "${PROJECT_ID}" \
  --schedule "0 0 * * *" \
  --time-zone "Europe/Stockholm" \
  --uri "${SERVICE_URL}/trigger" \
  --http-method POST \
  --headers "X-API-Key=$(gcloud secrets versions access latest --secret=orchestrator-trigger-key --project=${PROJECT_ID})" \
  --oidc-service-account-email "${SA}" \
  --oidc-token-audience "${SERVICE_URL}"

echo "Done! Blocket monitor deployed with hourly runs 06:00-00:00 Stockholm time."
