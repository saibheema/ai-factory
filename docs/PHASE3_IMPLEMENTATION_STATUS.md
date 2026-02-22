# Phase 3 Implementation Status

## Implemented hardening scaffolds

- Security CI workflow:
  - `.github/workflows/security.yml`
  - jobs: semgrep, gitleaks, pip-audit, trivy, checkov

- Preview deployment workflow scaffold:
  - `.github/workflows/preview.yml`

- Observability scaffolds:
  - `observability/prometheus/prometheus.yml`
  - `observability/grafana/provisioning/dashboards/llm-costs.json`

## Implemented runtime hardening

- Team LLM runtime governance:
  - `factory/llm/runtime.py`
  - LiteLLM proxy integration (best-effort) with per-team budget limits
  - governance snapshot endpoint: `GET /api/governance/budgets`
- Prometheus-style runtime metrics:
  - `factory/observability/metrics.py`
  - orchestrator endpoint: `GET /metrics`
  - counters/timers for core/full pipeline runs and clarification/QA events
- Preview deployment workflow is now functional with conditional Workload Identity auth:
  - `.github/workflows/preview.yml`
- Prometheus alert rules for pipeline SLO checks:
  - `observability/prometheus/alerts.yml`
- Incident delivery hooks with configurable channels:
  - `factory/observability/incident.py`
  - config endpoint: `GET /api/observability/incidents/config`
- Orchestrator full pipeline now routes handoff mismatch incidents via notifier hooks.

## Production naming alignment

- Primary pipeline API naming now supports production routes:
  - `POST /api/pipelines/core/run`
  - `GET /api/pipelines/core/example`
  - `POST /api/pipelines/full/run`
  - `GET /api/pipelines/full/teams`
  - `GET /api/pipelines/full/e2e`

- Deployment script naming now supports production routes:
  - `scripts/gcloud_deploy.sh`
  - `scripts/gcloud_managed_infra.sh`
  - `cloudbuild.release.yaml`

## Completion status

Phase 3 is complete.

Completed closure items:
1. Incident delivery hooks implemented (generic webhook, Slack, PagerDuty).
2. Grafana dashboard panels updated to consume current runtime counters and handoff/incident signals.
