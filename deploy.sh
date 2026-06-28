#!/bin/bash
# Deployment script for UCKhabar backend
# --cpu-always-allocated: required so APScheduler background jobs fire reliably
# --min-instances=1: prevents cold starts for users

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
  --cpu-always-allocated \
  --set-env-vars="GCP_PROJECT_ID=$(gcloud config get-value project),GCP_REGION=us-central1,APP_ENV=production,ADMIN_SECRET=${ADMIN_SECRET}"

echo "Deployment complete."
