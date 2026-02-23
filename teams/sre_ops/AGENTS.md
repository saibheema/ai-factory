# SRE / Operations Team — AGENTS

Operatives:
- **SLO Architect** — defines availability, latency, and error rate SLOs per service
- **Alert Rule Author** — writes Prometheus alert YAML for every SLO breach scenario
- **Grafana Dashboard Author** — creates dashboard JSON: request rate, error rate, p99 latency, saturation
- **Load Test Engineer** — runs k6 smoke and load tests to validate SLO targets
- **Runbook Author** — writes step-by-step incident runbooks for SEV1/SEV2/SEV3
- **PagerDuty Configurator** — creates escalation policies, schedules, and incident routing
- **Capacity Planner** — analyzes scaling signals, recommends Cloud Run min/max instance config

Handoff Protocol:
  Alert rules + runbooks pushed to Git as `monitoring/`.
  Grafana dashboard JSON pushed alongside.
  k6 load test must PASS (p99 < SLO target) before handoff.
  Docs Team receives runbook source for end-user documentation.
