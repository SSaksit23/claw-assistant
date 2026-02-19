#!/usr/bin/env bash
#
# Deploy Web365 ClawBot to Google Cloud Run.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated
#   - A GCP project selected: gcloud config set project PROJECT_ID
#
# Usage:
#   ./deploy.sh                     # Interactive (prompts for env vars)
#   ./deploy.sh --project my-proj   # Specify project explicitly
#
set -euo pipefail

PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null)}"
SERVICE_NAME="clawbot"
REGION="asia-southeast1"
IMAGE="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

if [ -z "$PROJECT_ID" ]; then
  echo "ERROR: No GCP project set. Run: gcloud config set project PROJECT_ID"
  exit 1
fi

echo "========================================"
echo "  Deploying Web365 ClawBot"
echo "  Project: ${PROJECT_ID}"
echo "  Region:  ${REGION}"
echo "  Image:   ${IMAGE}"
echo "========================================"

# ── Step 1: Build container image ──
echo ""
echo "[1/2] Building container image..."
gcloud builds submit --tag "${IMAGE}" --quiet

# ── Step 2: Deploy to Cloud Run ──
echo ""
echo "[2/2] Deploying to Cloud Run..."

# Check if required env vars are set
if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo ""
  echo "WARNING: OPENAI_API_KEY not set in environment."
  echo "Set it with: export OPENAI_API_KEY=sk-..."
  echo "Or pass via --set-env-vars when re-deploying."
  echo ""
fi

SECRET_KEY="${SECRET_KEY:-$(python3 -c 'import secrets; print(secrets.token_hex(32))' 2>/dev/null || echo 'change-me-in-production')}"

gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --region "${REGION}" \
  --memory 4Gi \
  --cpu 2 \
  --min-instances 1 \
  --max-instances 1 \
  --timeout 3600 \
  --session-affinity \
  --concurrency 80 \
  --set-env-vars "OPENAI_API_KEY=${OPENAI_API_KEY:-NOT_SET},SECRET_KEY=${SECRET_KEY},HEADLESS_MODE=True,FLASK_ENV=production,MAX_BROWSER_INSTANCES=10,BROWSER_IDLE_TIMEOUT=1800" \
  --allow-unauthenticated \
  --quiet

# ── Done ──
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --format='value(status.url)' 2>/dev/null)

echo ""
echo "========================================"
echo "  Deployment complete!"
echo "  URL: ${SERVICE_URL}"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Visit ${SERVICE_URL} and sign in with your qualityb2bpackage.com credentials"
echo "  2. Share the URL with your team (each user signs in with their own credentials)"
echo ""
echo "To update env vars later:"
echo "  gcloud run services update ${SERVICE_NAME} --region ${REGION} --set-env-vars KEY=VALUE"
echo ""
