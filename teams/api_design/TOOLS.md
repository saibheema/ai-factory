# API Design Team — TOOLS

Specification:
- **Git** (push): OpenAPI YAML to `openapi/spec.yaml` in project branch
- **Spectral**: Lint OpenAPI spec — zero errors required before handoff
- **OpenAI API**: Generate spec draft from Sol Arch ADR + requirement context

Documentation:
- **Google Docs**: API Contract Documentation (human-readable companion to spec YAML)
- **Mermaid**: Sequence diagrams for auth flows, create/read/update/delete scenarios

Tracking:
- **Plane**: API design issue linked to Sol Arch ADR, assigned to Backend Eng

Notifications:
- **Slack**: #api-design channel — spec published alert with Git branch + Doc links
- **Notification**: Stage-complete broadcast to Frontend Eng and Backend Eng
