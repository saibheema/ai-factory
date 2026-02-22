# AI Factory — Core/Full Pipeline MVP

This repository now contains a working Core/Full pipeline scaffold for the AI Software Factory plan.

## What is implemented

- Core configs:
  - `factory_config.yaml`
  - `litellm_config.yaml`
  - `docker-compose.yml`
  - `pyproject.toml`
- Orchestrator service (FastAPI):
  - `GET /health`
  - `GET /metrics`
  - `GET /api/settings/tools`
  - `POST /api/pipelines/core/run`
  - `POST /api/pipelines/full/run`
  - `POST /api/pipelines/full/run/async`
  - `GET /api/tasks/{task_id}`
  - `GET /api/governance/budgets`
  - `PUT /api/governance/teams/{team}`
  - `GET /api/projects/{project_id}/memory-map`
  - `POST /api/projects/{project_id}/chat`
  - `POST /api/projects/{project_id}/group-chat`
  - Clarification endpoints (schema-validated)
- Core pipeline with 5 teams:
  - `biz_analysis`
  - `solution_arch`
  - `backend_eng`
  - `qa_eng`
  - `docs_team`
- `TaskResult` model and guardrail validation
- Memory service API (`services/memory`) + remote memory client with fallback
- Clarification broker with Redis stream publish + TTL reply lookup
- Tool registry skeleton
- Chat service health endpoint
- Frontend dashboard modules:
  - Pipeline run (core/full)
  - Live agent progress tracker for async full pipeline tasks
  - Team model/budget settings
  - Project memory map
  - Project Q&A chat
  - Group chat planning with selected participants
- Team identity docs (`SOUL.md`, `AGENTS.md`, `TOOLS.md`) for the 5 core teams
- Baseline tests for task result, pipeline, and orchestrator endpoints

## Run (docker)

1. Start services:
   - `docker compose up --build`
2. Open:
   - Frontend: `http://localhost:3001`
   - Orchestrator health: `http://localhost:8000/health`
   - Chat health: `http://localhost:8001/health`
  - Memory health: `http://localhost:8006/health`

## Run tests

- `python3 -m compileall factory services tests`
- `python3 -m venv .venv && ./.venv/bin/pip install -r services/orchestrator/requirements.txt -r services/memory/requirements.txt -r services/clarification_responder/requirements.txt pytest`
- `./.venv/bin/python -m pytest tests -q`

## Deploy to Google Cloud Run

- Deployment script: `scripts/gcloud_deploy.sh`
- Cloud Build config: `cloudbuild.release.yaml`

Example:
- `PROJECT_ID=unicon-494419 REGION=us-central1 TAG=release-20260222 ./scripts/gcloud_deploy.sh`

This deploys:
- `ai-factory-memory`
- `ai-factory-orchestrator`
- `ai-factory-chat`
- `ai-factory-groupchat`
- `ai-factory-clarification-responder`
- `ai-factory-frontend`

## Provision managed GCP infra (Redis + Cloud SQL + VPC)

- Infra script: `scripts/gcloud_managed_infra.sh`

Example:
- `PROJECT_ID=unicon-494419 REGION=us-central1 ./scripts/gcloud_managed_infra.sh`

This provisions and wires:
- Serverless VPC connector (`ai-factory-connector`)
- Memorystore Redis (`ai-factory-redis`)
- Cloud SQL Postgres (`ai-factory-pg`) + DB/user
- Cloud Run redeploy with private networking and env wiring

Clarification responder behavior:
- background Redis stream consumer for core teams
- writes TTL responses to `clarification:reply:{request_id}`
- deployed with min instance = 1 in managed infra mode

Memory service behavior after managed setup:
- Writes/reads from Cloud SQL (`store=postgres` in API responses)
- Falls back to in-memory mode if DB is unreachable

Quick verify:
- `gcloud run services describe ai-factory-orchestrator --region us-central1 --format='value(status.url)'`
- `curl <ORCHESTRATOR_URL>/health`

Optional governance tagging:
- `PROJECT_ID=<id> ORG_ID=<org-id> ENV_VALUE=Development ./scripts/gcloud_project_env_tag.sh`

## Notes

This is a core pipeline implementation baseline focused on runnable system wiring and contracts.
Next iteration should add:
- persistence-backed memory storage (PostgreSQL/pgvector),
- clarification responder workers per team,
- real LLM orchestration per team objective,
- deeper integration tests and Langfuse callbacks.

## Phase 2 started

Starter endpoints are live:
- `GET /api/pipelines/full/teams`
- `POST /api/pipelines/full/run`
- `GET /api/pipelines/full/e2e`
- Groupchat service: `GET /health`, `POST /session/plan`
- Project Q&A endpoint: `POST /api/projects/{project_id}/qa`

Reference:
- `docs/PHASE2_KICKOFF.md`
- `teams/TEAM_CATALOG.yaml`
- `docs/PHASE2_IMPLEMENTATION_STATUS.md`

## Core pipeline functional example

- `GET /api/pipelines/core/example`
- returns:
  - 5 completed stages
  - simple operative artifacts from all core teams (`biz_analysis`, `solution_arch`, `backend_eng`, `qa_eng`, `docs_team`)

Project Q&A on stored memory:
- `POST /api/projects/{project_id}/qa`
- returns ranked memory matches and a concise answer.

Phase-2 run now also returns per-team artifacts with handoff metadata.
It also returns handoff validation:
- `handoffs` (expected vs observed per team)
- `overall_handoff_ok`

## Phase 3 hardening scaffolds

- Security workflow: `.github/workflows/security.yml`
- Preview workflow scaffold: `.github/workflows/preview.yml`
- Prometheus scrape config: `observability/prometheus/prometheus.yml`
- Grafana dashboard scaffold: `observability/grafana/provisioning/dashboards/llm-costs.json`

## Runtime governance and metrics

- Team-level LLM budget governance endpoint:
  - `GET /api/governance/budgets`
- Team-level settings update endpoint:
  - `PUT /api/governance/teams/{team}`
- Project memory map endpoint:
  - `GET /api/projects/{project_id}/memory-map`
- Project chat endpoint:
  - `POST /api/projects/{project_id}/chat`
- Project group-chat endpoint:
  - `POST /api/projects/{project_id}/group-chat`
- Prometheus-style metrics endpoint:
  - `GET /metrics`
- Incident notifier config endpoint:
  - `GET /api/observability/incidents/config`
- Full pipeline response now includes a `governance` section with team spend/limits.
