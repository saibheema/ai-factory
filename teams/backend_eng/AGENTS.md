# Backend Engineering Team — AGENTS

Operatives:
- **API Implementer** — writes all FastAPI route handlers following OpenAPI contract shapes exactly
- **Pydantic Model Author** — writes all request/response Pydantic v2 models with validators
- **Auth Middleware Engineer** — implements JWT/OAuth2 middleware as specified by Sol Arch
- **ORM Layer Author** — writes async SQLAlchemy models + queries matching Database Eng schema
- **Service Logic Engineer** — implements business logic layer (services/), separated from routes
- **Error Handler** — implements RFC 7807 Problem+JSON error responses for all 4xx/5xx cases
- **Test Author** — writes pytest unit + integration tests with ≥80% coverage
- **Observability Engineer** — adds structured JSON logging, request ID propagation, OTEL spans
- **GitHub PR Author** — opens PRs with conventional commits, links to API contract + Plane stories

Handoff Protocol:
  All routes pushed to Git branch `ai-factory/{project}/backend_eng`.
  pytest must PASS with ≥80% coverage before handoff.
  Database Eng receives ORM model mapping for schema verification via Slack.
  DevOps receives `requirements.txt` + health endpoint contract.
