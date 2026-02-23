# Solution Architecture Team — TOOLS

Research:
- **Tavily Search** (5 queries): UI framework landscape, backend comparison, cloud infra, security patterns, reference architectures
- **Firecrawl**: Crawl framework/vendor documentation and case studies
- **Wikipedia**: Architectural patterns (microservices, hexagonal, CQRS, event sourcing)
- **OpenAI API**: Tech spike analysis, tradeoff brainstorming, ADR draft review

Diagramming:
- **Mermaid**: C4 context diagram, C4 component diagram, sequence diagrams per integration

Documentation & Tracking:
- **Google Docs**: ADR document (primary deliverable + per-team handoff notes)
- **Google Sheets**: Tech Stack Decision Matrix (options evaluated, decision, rationale, owner per area)
- **Confluence**: Published ADR page linked from all team spaces
- **Plane**: ADR issue with links to Doc + Sheet, assigned to each affected team

Notifications:
- **Slack**: #architecture channel — ADR summary + tech stack one-liner + handoff links
- **Notification**: Stage-complete broadcast to all downstream teams

Validation:
- **ADR Template Checklist**: Context → Options → Decision → Consequences → Handoffs → Status
- **Threat-model checklist**: Reviewed by Security Liaison before ADR is marked Accepted
- **API contract validator**: Confirms API protocol choice aligns with downstream capability
