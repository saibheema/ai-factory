#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project)}"
REGION="${REGION:-us-central1}"
REPO="${REPO:-ai-factory}"
TAG="${TAG:-phase1}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "PROJECT_ID is not set and no default gcloud project is configured."
  exit 1
fi

echo "Using PROJECT_ID=${PROJECT_ID}, REGION=${REGION}, REPO=${REPO}, TAG=${TAG}"

gcloud config set project "${PROJECT_ID}" >/dev/null

# Best-effort project environment tagging (ORG_ID required)
ENV_VALUE="${ENV_VALUE:-Development}" ORG_ID="${ORG_ID:-}" PROJECT_ID="${PROJECT_ID}" bash ./scripts/gcloud_project_env_tag.sh || true

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com

if ! gcloud artifacts repositories describe "${REPO}" --location "${REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${REPO}" \
    --repository-format docker \
    --location "${REGION}" \
    --description "AI Factory containers"
fi

BASE_IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"

# Build containers
gcloud builds submit . \
  --config cloudbuild.release.yaml \
  --substitutions "_BASE_IMAGE=${BASE_IMAGE},_TAG=${TAG}"

# Deploy memory first

gcloud run deploy ai-factory-memory \
  --image "${BASE_IMAGE}/memory:${TAG}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated

MEMORY_URL="$(gcloud run services describe ai-factory-memory --region "${REGION}" --format='value(status.url)')"

# Deploy LiteLLM proxy
gcloud run deploy ai-factory-litellm \
  --image "${BASE_IMAGE}/litellm:${TAG}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --port 4000 \
  --set-secrets "GEMINI_API_KEY=GEMINI_API_KEY:latest"

LITELLM_URL="$(gcloud run services describe ai-factory-litellm --region "${REGION}" --format='value(status.url)')"

# Deploy orchestrator with memory URL

gcloud run deploy ai-factory-orchestrator \
  --image "${BASE_IMAGE}/orchestrator:${TAG}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "MEMORY_SERVICE_URL=${MEMORY_URL},REDIS_HOST=localhost"

ORCHESTRATOR_URL="$(gcloud run services describe ai-factory-orchestrator --region "${REGION}" --format='value(status.url)')"

# Deploy chat

gcloud run deploy ai-factory-chat \
  --image "${BASE_IMAGE}/chat:${TAG}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated

# Deploy groupchat (phase 2 starter)
gcloud run deploy ai-factory-groupchat \
  --image "${BASE_IMAGE}/groupchat:${TAG}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated

GROUPCHAT_URL="$(gcloud run services describe ai-factory-groupchat --region "${REGION}" --format='value(status.url)')"

# Re-deploy orchestrator with full runtime wiring (LLM + groupchat)
gcloud run deploy ai-factory-orchestrator \
  --image "${BASE_IMAGE}/orchestrator:${TAG}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "MEMORY_SERVICE_URL=${MEMORY_URL},REDIS_HOST=localhost,ENABLE_LLM_RUNTIME=true,LITELLM_PROXY_URL=${LITELLM_URL},GROUPCHAT_SERVICE_URL=${GROUPCHAT_URL}"

# Deploy clarification responder

gcloud run deploy ai-factory-clarification-responder \
  --image "${BASE_IMAGE}/clarification-responder:${TAG}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "^~^REDIS_HOST=localhost~REDIS_PORT=6379~RESPONDER_TEAMS=biz_analysis,solution_arch,backend_eng,qa_eng,docs_team"

# Deploy frontend and point it to orchestrator

gcloud run deploy ai-factory-frontend \
  --image "${BASE_IMAGE}/frontend:${TAG}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "VITE_API_BASE_URL=${ORCHESTRATOR_URL}"

echo "Deployment complete"
echo "Memory:       ${MEMORY_URL}"
echo "Orchestrator: ${ORCHESTRATOR_URL}"
echo "LiteLLM:      ${LITELLM_URL}"
echo "Chat:         $(gcloud run services describe ai-factory-chat --region "${REGION}" --format='value(status.url)')"
echo "GroupChat:    $(gcloud run services describe ai-factory-groupchat --region "${REGION}" --format='value(status.url)')"
echo "Responder:    $(gcloud run services describe ai-factory-clarification-responder --region "${REGION}" --format='value(status.url)')"
echo "Frontend:     $(gcloud run services describe ai-factory-frontend --region "${REGION}" --format='value(status.url)')"
