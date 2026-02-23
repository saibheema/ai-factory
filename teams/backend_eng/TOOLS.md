# Backend Engineering Team — TOOLS

Code & Quality:
- **Git** (push): FastAPI app to `app/` in project branch
- **GitHub API**: Open PRs with conventional commits + Plane story links
- **Ruff**: Python linter — zero violations required before handoff
- **Black**: Python formatter — consistent code style
- **mypy**: Type checking — no type errors in service layer
- **pytest**: Unit + integration tests — ≥80% coverage gate
- **Bandit**: Python SAST — no HIGH findings
- **Sandbox**: Run service in isolated environment for integration validation

Data Layer:
- **SQL Tool**: Validate queries against dev database
- **Redis**: Test cache integration (session, rate limiting)

Container:
- **Docker**: Build + validate container image
- **GCS**: Artifact backup for build outputs

Tracking:
- **Plane**: Implementation issues per endpoint, linked to API contract

Notifications:
- **Slack**: #backend channel — implementation complete with test coverage + PR link
- **Notification**: Stage-complete broadcast to Database Eng and DevOps
