#!/bin/bash
# Deployment script for UCKhabar backend
# Ensures --min-instances=1 is passed so APScheduler doesn't die from cold starts

set -e

echo "Deploying UCKhabar Backend to Cloud Run..."

# Build and deploy
gcloud run deploy uckhabar-backend \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --min-instances=1 \
  --set-env-vars="GCP_PROJECT_ID=$(gcloud config get-value project),GCP_REGION=us-central1,APP_ENV=production"

echo "Deployment complete."
