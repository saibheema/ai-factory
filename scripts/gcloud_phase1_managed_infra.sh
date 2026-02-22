#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project)}"
REGION="${REGION:-us-central1}"
VPC_CONNECTOR="${VPC_CONNECTOR:-ai-factory-connector}"
REDIS_INSTANCE="${REDIS_INSTANCE:-ai-factory-redis}"
SQL_INSTANCE="${SQL_INSTANCE:-ai-factory-pg}"
SQL_DB="${SQL_DB:-factory}"
SQL_USER="${SQL_USER:-factory_user}"
TAG="${TAG:-phase1-20260221}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "PROJECT_ID is not set and no default gcloud project is configured."
  exit 1
fi

echo "Using PROJECT_ID=${PROJECT_ID}, REGION=${REGION}"

gcloud config set project "${PROJECT_ID}" >/dev/null

# Best-effort project environment tagging (ORG_ID required)
ENV_VALUE="${ENV_VALUE:-Development}" ORG_ID="${ORG_ID:-}" PROJECT_ID="${PROJECT_ID}" bash ./scripts/gcloud_project_env_tag.sh || true

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  redis.googleapis.com \
  sqladmin.googleapis.com \
  vpcaccess.googleapis.com \
  servicenetworking.googleapis.com \
  secretmanager.googleapis.com

# Private Service Access (required for Memorystore + private Cloud SQL)
if ! gcloud compute addresses describe google-managed-services-default --global >/dev/null 2>&1; then
  gcloud compute addresses create google-managed-services-default \
    --global \
    --purpose=VPC_PEERING \
    --prefix-length=16 \
    --network=default
fi

if ! gcloud services vpc-peerings list \
  --network=default \
  --service=servicenetworking.googleapis.com \
  --format='value(state)' | grep -q "ACTIVE"; then
  gcloud services vpc-peerings connect \
    --service=servicenetworking.googleapis.com \
    --network=default \
    --ranges=google-managed-services-default
fi

# Create VPC connector for Cloud Run -> private resources (Redis/SQL private IP)
if ! gcloud compute networks vpc-access connectors describe "${VPC_CONNECTOR}" --region "${REGION}" >/dev/null 2>&1; then
  gcloud compute networks vpc-access connectors create "${VPC_CONNECTOR}" \
    --region "${REGION}" \
    --network default \
    --range 10.8.0.0/28
fi

# Create Memorystore Redis
if ! gcloud redis instances describe "${REDIS_INSTANCE}" --region "${REGION}" >/dev/null 2>&1; then
  gcloud redis instances create "${REDIS_INSTANCE}" \
    --size=1 \
    --region "${REGION}" \
    --redis-version=redis_7_0 \
    --network=default \
    --connect-mode=private-service-access
fi

# Create Cloud SQL Postgres instance
if ! gcloud sql instances describe "${SQL_INSTANCE}" >/dev/null 2>&1; then
  gcloud sql instances create "${SQL_INSTANCE}" \
    --database-version=POSTGRES_16 \
    --edition=ENTERPRISE \
    --cpu=1 \
    --memory=3840MiB \
    --region="${REGION}" \
    --network=default \
    --no-assign-ip
fi

if ! gcloud sql databases describe "${SQL_DB}" --instance "${SQL_INSTANCE}" >/dev/null 2>&1; then
  gcloud sql databases create "${SQL_DB}" --instance "${SQL_INSTANCE}"
fi

if ! gcloud sql users list --instance "${SQL_INSTANCE}" --format='value(name)' | grep -qx "${SQL_USER}"; then
  SQL_PASSWORD="$(openssl rand -base64 24 | tr -d '\n')"
  gcloud sql users create "${SQL_USER}" --instance "${SQL_INSTANCE}" --password "${SQL_PASSWORD}"
  printf "%s" "${SQL_PASSWORD}" | gcloud secrets create ai-factory-sql-password --data-file=- >/dev/null 2>&1 || \
    printf "%s" "${SQL_PASSWORD}" | gcloud secrets versions add ai-factory-sql-password --data-file=- >/dev/null
fi

REDIS_HOST="$(gcloud redis instances describe "${REDIS_INSTANCE}" --region "${REGION}" --format='value(host)')"
REDIS_PORT="$(gcloud redis instances describe "${REDIS_INSTANCE}" --region "${REGION}" --format='value(port)')"
SQL_CONN="$(gcloud sql instances describe "${SQL_INSTANCE}" --format='value(connectionName)')"
MEMORY_URL="$(gcloud run services describe ai-factory-memory --region "${REGION}" --format='value(status.url)')"
LITELLM_URL="$(gcloud run services describe ai-factory-litellm --region "${REGION}" --format='value(status.url)' 2>/dev/null || true)"
GROUPCHAT_URL="$(gcloud run services describe ai-factory-groupchat --region "${REGION}" --format='value(status.url)' 2>/dev/null || true)"

# Ensure runtime service account can access Cloud SQL
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/cloudsql.client" >/dev/null

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor" >/dev/null

# Redeploy memory with Cloud SQL attachment and VPC connector

gcloud run deploy ai-factory-memory \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --image "${REGION}-docker.pkg.dev/${PROJECT_ID}/ai-factory/memory:${TAG}" \
  --vpc-connector "${VPC_CONNECTOR}" \
  --vpc-egress private-ranges-only \
  --add-cloudsql-instances "${SQL_CONN}" \
  --set-env-vars "DB_HOST=/cloudsql/${SQL_CONN},DB_NAME=${SQL_DB},DB_USER=${SQL_USER}" \
  --set-secrets "DB_PASSWORD=ai-factory-sql-password:latest"

# Redeploy orchestrator with Redis private IP and VPC connector

gcloud run deploy ai-factory-orchestrator \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --image "${REGION}-docker.pkg.dev/${PROJECT_ID}/ai-factory/orchestrator:${TAG}" \
  --vpc-connector "${VPC_CONNECTOR}" \
  --vpc-egress private-ranges-only \
  --set-env-vars "MEMORY_SERVICE_URL=${MEMORY_URL},REDIS_HOST=${REDIS_HOST},REDIS_PORT=${REDIS_PORT},ENABLE_LLM_RUNTIME=true,LITELLM_PROXY_URL=${LITELLM_URL},GROUPCHAT_SERVICE_URL=${GROUPCHAT_URL}"

# Redeploy clarification responder with Redis private IP and VPC connector
gcloud run deploy ai-factory-clarification-responder \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --image "${REGION}-docker.pkg.dev/${PROJECT_ID}/ai-factory/clarification-responder:${TAG}" \
  --vpc-connector "${VPC_CONNECTOR}" \
  --vpc-egress private-ranges-only \
  --min-instances 1 \
  --set-env-vars "^~^REDIS_HOST=${REDIS_HOST}~REDIS_PORT=${REDIS_PORT}~RESPONDER_TEAMS=biz_analysis,solution_arch,backend_eng,qa_eng,docs_team"

echo "Managed infra setup complete"
echo "VPC Connector: ${VPC_CONNECTOR}"
echo "Redis: ${REDIS_INSTANCE} ${REDIS_HOST}:${REDIS_PORT}"
echo "Cloud SQL: ${SQL_INSTANCE} (${SQL_CONN})"
