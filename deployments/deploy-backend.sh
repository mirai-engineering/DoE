#!/bin/bash
set -e

# Configure your GCP project ID here
PROJECT_ID="your-gcp-project"
REGION="europe-west1"
SERVICE_NAME="kidney-segmentation"

[ -z "$CORS_ORIGINS" ] && { 
  echo "ERROR: CORS_ORIGINS must be set"
  echo "Example: export CORS_ORIGINS='https://your-frontend.vercel.app'"
  exit 1
}

docker build -t gcr.io/$PROJECT_ID/$SERVICE_NAME-backend:latest ./backend
docker push gcr.io/$PROJECT_ID/$SERVICE_NAME-backend:latest

BACKEND_URL=$(gcloud run deploy $SERVICE_NAME-backend \
  --image gcr.io/$PROJECT_ID/$SERVICE_NAME-backend:latest \
  --platform managed --region $REGION \
  --memory 2Gi --cpu 2 --timeout 120s --allow-unauthenticated \
  --set-env-vars "CORS_ORIGINS=$CORS_ORIGINS,ENVIRONMENT=production,MODEL_PATH=/app/models/kidney_segmentation.onnx" \
  --format 'value(status.url)')

echo "Backend URL: $BACKEND_URL"
echo "Deploy frontend with: BACKEND_URL=$BACKEND_URL ./deploy-frontend.sh"
