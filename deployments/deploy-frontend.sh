#!/bin/bash
set -e

[ -z "$BACKEND_URL" ] && { 
  echo "ERROR: BACKEND_URL must be set"
  echo "Example: export BACKEND_URL='https://your-backend.run.app'"
  exit 1
}

command -v vercel &> /dev/null || npm install -g vercel

cd frontend
VITE_API_URL=$BACKEND_URL npm run build
vercel --prod --env VITE_API_URL=$BACKEND_URL

