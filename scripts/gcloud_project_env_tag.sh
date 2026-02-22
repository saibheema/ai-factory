#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project)}"
ENV_VALUE="${ENV_VALUE:-Development}"
TAG_KEY_SHORT="${TAG_KEY_SHORT:-environment}"
ORG_ID="${ORG_ID:-}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "PROJECT_ID is not set."
  exit 1
fi

if [[ -z "${ORG_ID}" ]]; then
  echo "ORG_ID not provided. Skipping tag key/value creation."
  echo "To enable automation: set ORG_ID and rerun."
  exit 0
fi

if ! [[ "${ORG_ID}" =~ ^[0-9]+$ ]]; then
  CANDIDATE="$(echo "${ORG_ID}" | tr '[:upper:]' '[:lower:]')"
  RESOLVED_ORG_ID="$(gcloud organizations list --format=json \
    | python3 -c 'import sys,json; c=sys.argv[1].lower(); orgs=json.load(sys.stdin); 
for o in orgs:
  n=(o.get("name","") or "")
  d=(o.get("displayName","") or "")
  if c in d.lower() or c in n.lower():
    print(n.split("/")[-1]);
    break' "${CANDIDATE}")"
  if [[ -z "${RESOLVED_ORG_ID}" ]]; then
    echo "Unable to resolve ORG_ID='${ORG_ID}' to a numeric organization id."
    exit 1
  fi
  ORG_ID="${RESOLVED_ORG_ID}"
fi

KEY_PARENT="organizations/${ORG_ID}"

# Create/find tag key
TAG_KEY_NAME="$(gcloud resource-manager tags keys list --parent="${KEY_PARENT}" --format='value(name)' --filter="shortName=${TAG_KEY_SHORT}" | head -n1 || true)"
if [[ -z "${TAG_KEY_NAME}" ]]; then
  gcloud resource-manager tags keys create "${TAG_KEY_SHORT}" --parent="${KEY_PARENT}"
  TAG_KEY_NAME="$(gcloud resource-manager tags keys list --parent="${KEY_PARENT}" --format='value(name)' --filter="shortName=${TAG_KEY_SHORT}" | head -n1)"
fi

# Create/find tag value
TAG_VALUE_NAME="$(gcloud resource-manager tags values list --parent="${TAG_KEY_NAME}" --format='value(name)' --filter="shortName=${ENV_VALUE}" | head -n1 || true)"
if [[ -z "${TAG_VALUE_NAME}" ]]; then
  gcloud resource-manager tags values create "${ENV_VALUE}" --parent="${TAG_KEY_NAME}"
  TAG_VALUE_NAME="$(gcloud resource-manager tags values list --parent="${TAG_KEY_NAME}" --format='value(name)' --filter="shortName=${ENV_VALUE}" | head -n1)"
fi

# Bind tag value to project
PROJECT_FULL="//cloudresourcemanager.googleapis.com/projects/${PROJECT_ID}"

if ! gcloud resource-manager tags bindings list --parent="${PROJECT_FULL}" --format='value(name)' | grep -q "${TAG_VALUE_NAME}"; then
  gcloud resource-manager tags bindings create --parent="${PROJECT_FULL}" --tag-value="${TAG_VALUE_NAME}"
fi

echo "Environment tag ensured: ${TAG_KEY_SHORT}=${ENV_VALUE} for ${PROJECT_ID}"
