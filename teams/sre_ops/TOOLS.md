# SRE / Operations Team — TOOLS

Observability:
- **Git** (push): Prometheus alert YAML + Grafana dashboard JSON to `monitoring/` branch
- **GitHub API**: Open PR for monitoring changes

Load Testing:
- **k6**: Smoke test (< 10 VUs) + load test (target VUs at SLO latency) against deployment URL

Runtime Management:
- **kubectl**: Inspect pod health, logs, resource usage on GKE
- **Helm**: Manage release versions + rollback
- **Cloud Run**: List revisions, check error rates, manage traffic splits
- **Redis**: Inspect cache hit rate and memory usage

Incident Management:
- **PagerDuty**: Create incident policies and escalation schedules

Documentation:
- **Google Docs**: Operations Runbook (service overview, SLOs, on-call steps, rollback)

Security:
- **Trivy**: Runtime image CVE scan on deployed containers

Tracking:
- **Plane**: SLO issue per service, linked to DevOps deployment issues

Notifications:
- **Slack**: #sre channel — SLO baselines + k6 load test results
- **Notification**: Stage-complete broadcast to Docs Team
