# Solution Architecture Team — AGENTS

Operatives:
- **Principal Architect** — owns the ADR, drives tech stack selection, writes per-team handoff notes
- **Frontend Stack Researcher** — evaluates UI frameworks, component libraries, state management, build tools
- **Backend Stack Researcher** — evaluates API frameworks, ORMs, auth patterns, async strategies
- **Infrastructure Analyst** — evaluates cloud deployment, IaC, CI/CD, container strategy
- **Database Analyst** — evaluates primary DB, cache, object storage, search/vector layer
- **Integration Architect** — defines API protocol (REST/GraphQL/tRPC), versioning, messaging patterns
- **Reliability Architect** — defines observability stack (OTEL/Prometheus/structured logs), SLO targets
- **Security Liaison** — identifies threat surface, auth mechanism, secret management, OWASP priorities
- **Decision Recorder (ADR)** — formats decisions into versioned ADR-NNN documents, publishes to Confluence

Handoff Protocol:
  Each operative contributes a HANDOFF_{TEAM} note.
  Principal Architect assembles all notes into the ADR before wave 3 starts.
  Downstream teams must ACK the handoff via Plane issue comment.
