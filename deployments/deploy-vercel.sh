#!/bin/bash
# deploy-vercel.sh — Deploy the DoE backend on Vercel Serverless Functions
# Usage: ./deploy-vercel.sh [--env staging|production] [--token <vercel-token>] [--project <vercel-project>]
set -e

# ── Config ──────────────────────────────────────────────────────────
ENV="${1:-staging}"
DEPLOY_PROJECT="${DOE_VERCEL_PROJECT:-doe-backend-staging}"
DEPLOY_TOKEN="${DOE_VERCEL_TOKEN:-}"

# ── Ensure vercel CLI is available ──────────────────────────────────
if ! command -v vercel &>/dev/null; then
   echo "ERROR: @vercel/cli not found. Install with: npm i -g @vercel/cli"
   exit 1
fi

# ── Build output structure ──────────────────────────────────────────
VLS_FUNCTIONS_DIR="deployments/vercel-funcs"
mkdir -p "$VLS_FUNCTIONS_DIR/api"

echo "[1/6] Generating VLS serverless entry points …"

cat > "$VLS_FUNCTIONS_DIR/vercel.json" <<'JSON'
{
  "version": 2,
  "functions": {
    "api/*.py": {
      "runtime": "python3.11@2.0.0"
    }
  },
  "env": {
    "DOE_VERCEL_BUILD": "true",
    "ENVIRONMENT": "staging"
  },
  "routes": [
    { "src": "/api/(.*)", "dest": "api/$1" },
    { "src": "/health", "dest": "api/health" }
  ]
}
JSON

cat > "$VLS_FUNCTIONS_DIR/api/health.py" <<'PY'
import fastapi
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "mirai-doe-engine-api",
        "platform": "vercel-serverless",
        "available_projects": ["pem_fuel_cell_demo", "pem_fuel_cell_real_cathode_degradation"]
    }
PY

cat > "$VLS_FUNCTIONS_DIR/requirements.txt" <<'REQ'
fastapi>=0.110.0
uvicorn>=0.29.0
pydantic>=2.6.0
numpy>=1.26.0
pandas>=2.2.0
ONNX>=1.16.0
requests>=2.31.0
jsonschema>=4.21.0
REQ

# ── Deploy ──────────────────────────────────────────────────────────
echo "[2/6] Pushing to Vercel …"
DEPLOY_CMD="vercel deploy --yes --prod --confirm --token '$DEPLOY_TOKEN'"

echo "[3/6] Setting Vercel env vars …"
eval $DEPLOY_CMD

echo "[4/6] Deploy URL example: https://<prod-url>/.vercel"
echo "[5/6] Caveats for ML workloads on Vercel:"
echo "     • Max duration: 10s (Hobby) | 60s (Pro) | 300s (Enterprise)"
echo "     • Cold starts: ~1-3s for Python on the first invocation"
echo "     • Large ONNX models: fetch from S3/GCS at build or runtime"
echo "     • WebSockets & streaming: not supported"
echo "[6/6] See: https://vercel.com/docs/functions/serverless-functions/runtimes/python"
