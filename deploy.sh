#!/bin/bash
# Deployment script for UCKhabar backend
# --min-instances=1: prevents cold starts for users
# NOTE: cpu-always-allocated is NOT set — Cloud Scheduler (not APScheduler) handles
# background jobs via HTTP, so the instance only needs CPU during actual requests.

set -e

echo "Deploying UCKhabar Backend to Cloud Run..."

if [ -z "$ADMIN_SECRET" ]; then
  echo "ERROR: ADMIN_SECRET environment variable is not set."
  echo "Run: export ADMIN_SECRET=your_secret_here"
  exit 1
fi

gcloud run deploy uckhabar-backend \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --min-instances=1 \
  --cpu=0.5 \
  --memory=512Mi \
  --set-env-vars="GCP_PROJECT_ID=$(gcloud config get-value project),GCP_REGION=us-central1,APP_ENV=production,ADMIN_SECRET=${ADMIN_SECRET}"

echo "Deployment complete."
