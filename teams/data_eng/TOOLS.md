# Data Engineering Team — TOOLS

Code:
- **Git** (push): ETL scripts to `pipelines/` in project branch
- **GitHub API**: Open PRs for pipeline changes
- **GCS**: Artifact backup for pipeline configs and intermediate data
- **mypy**: Type-check pipeline Python code

Data Sources/Destinations:
- **SQL Tool**: Execute PostgreSQL queries for extract and load validation
- **BigQuery**: Create datasets, run DML for analytics mart loads
- **CSV**: Ingest and validate flat-file data sources

Tracking:
- **Plane**: Pipeline issue per ETL job, linked to Database Eng schema

Notifications:
- **Slack**: #data-eng channel — pipeline deployed with schedule + SLA
- **Notification**: Stage-complete broadcast to ML Eng
