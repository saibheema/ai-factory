# Data Engineering Team — AGENTS

Operatives:
- **Pipeline Architect** — designs ETL/ELT flow, partitioning strategy, scheduling
- **Extract Engineer** — implements source connectors (API, DB, GCS, CSV ingestion)
- **Transform Engineer** — writes and unit-tests data transformation functions
- **Load Engineer** — manages destination writes (PostgreSQL, BigQuery) with upsert/merge logic
- **Data Quality Monitor** — writes quality checks (row counts, null %, referential integrity)
- **mypy Type Checker** — ensures pipeline Python code is type-annotated and mypy-clean

Handoff Protocol:
  Pipeline Architect pushes `pipelines/` to Git.
  ML Eng receives training dataset location + schema via Slack.
