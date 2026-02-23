# Database Engineering Team — AGENTS

Operatives:
- **Schema Architect** — designs the entity-relationship model, normalization strategy, naming conventions
- **Migration Author** — writes versioned DDL migrations (CREATE TABLE, ALTER, INDEX, constraints)
- **Index Strategist** — identifies all query patterns from API contract and creates appropriate indexes
- **Data Dictionary Author** — documents every table/column (type, nullable, default, description)
- **SQL Test Author** — writes integration tests for constraints, triggers, and stored procedures
- **BigQuery Analyst** — creates analytics views or BigQuery exports for reporting workloads
- **ER Diagram Author** — generates ER diagrams from schema for documentation

Handoff Protocol:
  Schema Architect pushes `migrations/` to Git.
  Data Dictionary published to Google Docs.
  Backend Eng receives schema + ORM mapping verification via Slack.
