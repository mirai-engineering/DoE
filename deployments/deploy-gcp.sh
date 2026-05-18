#!/bin/bash
# deploy-gcp.sh — Deploy the DoE backend to GCP Cloud Run
# Usage: ./deploy-gcp.sh [--env staging|production] [--project <gcp-project>]
set -e

PROJECT_ID="${DOE_GCP_PROJECT:-your-gcp-project}"
REGION="${DOE_GCP_REGION:-us-central1}"
ENV="${1:---env staging}"
PROJECT_FLAG="${2:---project $PROJECT_ID}"

# ── Build & Push ──────────────────────────────────────────────────
echo "[1/4] Building & pushing Docker image to GCR …"
IMAGE_TAG="gcr.io/$PROJECT_ID/doe-backend:latest"
docker build -t "$IMAGE_TAG" ./backend
docker push "$IMAGE_TAG"

# ── Config ────────────────────────────────────────────────────────
SERVICE_NAME="doe-backend"
echo "[2/4] Deploying Cloud Run …"

export CLOUDRUN_ARGS=(
  --image "$IMAGE_TAG"
  --platform managed
  --region "$REGION"
  --port 8000
  --memory 2Gi
  --cpu 2
  --timeout 120s
  --allow-unauthenticated
  --vpc-connector "$PROJECT:_vpc-connector"
  --set-env-vars "ENVIRONMENT=production,DOE_DISABLE_MLFLOW_MODEL_LOADING=0"
  --set-env-vars "MLFLOW_TRACKING_URI=$MLFLOW_HOST"
  --set-secrets "MLFLOW_CREDENTIALS=mlflow-creds:latest"
)

SERVICE_URL=$(gcloud run deploy \
  "$SERVICE_NAME" \
  "${CLOUDRUN_ARGS[@]}" \
  --format 'value(status.url)')

echo "[3/4] Service URL: $SERVICE_URL"
echo "[4/4] Set MLFLOW_HOST to point to a secure MLflow server"
echo "Example: export MLFLOW_HOST=https://mlflow-gcp.yourproject.com"
