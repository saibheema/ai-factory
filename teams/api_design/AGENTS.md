# API Design Team — AGENTS

Operatives:
- **API Architect** — owns the OpenAPI spec, enforces RESTful conventions / protocol chosen by Sol Arch
- **Schema Designer** — defines request/response Pydantic/JSON Schema models, enums, nullable fields
- **Auth Flow Designer** — specifies OAuth2/JWT flows, scopes, token lifecycle, refresh strategy
- **Error Standards Owner** — defines RFC 7807 Problem+JSON shape used across all endpoints
- **Sequence Diagrammer** — draws Mermaid sequence diagrams per integration scenario
- **Spectral Linter** — runs Spectral ruleset, ensures zero lint errors before handoff
- **Contract Doc Author** — writes human-readable API contract doc in Google Docs

Handoff Protocol:
  API Architect pushes openapi/spec.yaml to Git branch `ai-factory/{project}/{team}`.
  Spectral lint must PASS before handoff.
  Frontend Eng and Backend Eng both receive a Slack notification with the spec URL.
