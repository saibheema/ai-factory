# Database Engineering Team — TOOLS

Schema & Migrations:
- **Git** (push): DDL migration files to `migrations/` in project branch
- **GitHub API**: Open PRs for schema changes with rollback plan in description
- **SQL Tool**: Execute schema validation queries against dev database

Analytics:
- **BigQuery**: Create views and export tables for analytics workloads
- **CSV**: Import and validate seed data or test datasets

Documentation:
- **Google Docs**: Data Dictionary (table/column reference)
- **GCS**: Schema artifact backup

Tracking:
- **Plane**: Schema issue per migration, linked to Backend Eng Plane stories

Notifications:
- **Slack**: #database channel — schema migration complete with ER diagram link
- **Notification**: Stage-complete broadcast to Backend Eng and Data Eng
