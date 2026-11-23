#!/usr/bin/env bash
# Deploy FinnWinn to Google Cloud Run (backend first, then frontend).
# Run from the repo root in Google Cloud Shell:   bash deploy/cloudrun-deploy.sh
# Re-run it any time to redeploy after pushing changes (git pull first).
set -euo pipefail

REGION="${REGION:-asia-southeast1}"          # Singapore: same city as the Neon database
API_SERVICE="finnwinn-api"
WEB_SERVICE="finnwinn-web"

cd "$(dirname "$0")/.."

for f in deploy/backend.env.yaml deploy/frontend.env.yaml; do
  if [ ! -f "$f" ]; then
    echo "Missing $f - copy ${f%.env.yaml}.env.example.yaml to $f and fill it in."; exit 1
  fi
done
if grep -q 'CHANGE_ME' deploy/backend.env.yaml; then
  echo "deploy/backend.env.yaml still has CHANGE_ME values (generate with: openssl rand -hex 32)"; exit 1
fi

PROJECT="$(gcloud config get-value project 2>/dev/null)"
if [ -z "$PROJECT" ]; then echo "No project set. Run: gcloud config set project YOUR_PROJECT_ID"; exit 1; fi
echo "Project: $PROJECT | Region: $REGION"

echo "==> Enabling required APIs (first run only takes a minute)"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com --quiet

echo "==> Deploying backend ($API_SERVICE)"
# max-instances 1: wallets/caches have in-memory fallbacks, so keep a single instance for now.
gcloud run deploy "$API_SERVICE" \
  --source backend \
  --region "$REGION" \
  --allow-unauthenticated \
  --env-vars-file deploy/backend.env.yaml \
  --memory 1Gi --cpu 1 \
  --min-instances 0 --max-instances 1 \
  --timeout 300 \
  --quiet

API_URL="$(gcloud run services describe "$API_SERVICE" --region "$REGION" --format='value(status.url)')"
echo "Backend URL: $API_URL"

# Frontend settings = frontend.env.yaml + backend URL + the same service key as the backend.
WEB_ENV="$(mktemp)"
trap 'rm -f "$WEB_ENV"' EXIT
cat deploy/frontend.env.yaml > "$WEB_ENV"
echo "" >> "$WEB_ENV"
echo "BACKEND_URL: \"$API_URL\"" >> "$WEB_ENV"
grep -E '^INTERNAL_SERVICE_KEY:' deploy/backend.env.yaml >> "$WEB_ENV"

echo "==> Deploying frontend ($WEB_SERVICE)"
gcloud run deploy "$WEB_SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --env-vars-file "$WEB_ENV" \
  --memory 512Mi --cpu 1 \
  --min-instances 0 --max-instances 3 \
  --timeout 300 \
  --quiet

WEB_URL="$(gcloud run services describe "$WEB_SERVICE" --region "$REGION" --format='value(status.url)')"
echo ""
echo "Done. FinnWinn is live at: $WEB_URL"
