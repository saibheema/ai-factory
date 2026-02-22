#!/usr/bin/env bash
set -euo pipefail

# Production naming wrapper
exec "$(dirname "$0")/gcloud_phase1_managed_infra.sh" "$@"
