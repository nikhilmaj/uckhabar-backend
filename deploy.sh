#!/bin/bash
# Deployment script for UCKhabar backend
# --min-instances=0       : scales to zero when idle — literally $0 cost when not processing requests
# --timeout=300           : allows admin endpoints (RSS poll, scoring) up to 5 min
# --concurrency=80        : FastAPI is async; handle many requests per instance
# --cpu-always-allocated is NOT set — Cloud Scheduler triggers admin jobs via HTTP,
#   CPU is only billed during actual request processing.

set -e

echo "Deploying UCKhabar Backend to Cloud Run (asia-south1)..."

if [ -z "$ADMIN_SECRET" ]; then
  echo "ERROR: ADMIN_SECRET environment variable is not set."
  echo "Run: export ADMIN_SECRET=your_secret_here"
  exit 1
fi

gcloud run deploy uckhabar-backend \
  --source . \
  --project uckhabar \
  --region asia-south1 \
  --allow-unauthenticated \
  --min-instances=0 \
  --max-instances=3 \
  --cpu=1 \
  --memory=512Mi \
  --timeout=300 \
  --concurrency=80 \
  --set-env-vars="GCP_PROJECT_ID=uckhabar,GCP_REGION=asia-south1,APP_ENV=production,ADMIN_SECRET=${ADMIN_SECRET}"

echo "Deployment complete."
