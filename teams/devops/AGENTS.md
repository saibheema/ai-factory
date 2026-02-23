# DevOps Team — AGENTS

Operatives:
- **Dockerfile Author** — minimal, multi-stage, non-root, no secrets in layers
- **CI/CD Pipeline Author** — GitHub Actions / Cloud Build: lint → test → SAST → build → push → deploy
- **Terraform Author** — cloud resources: Cloud Run service, VPC, IAM, Secret Manager, Cloud Armor
- **Container Security Reviewer** — runs Trivy on all images, Checkov on IaC, Gitleaks on configs
- **Scaling Config Engineer** — configures Cloud Run min/max instances, concurrency, CPU/memory
- **Secret Manager Engineer** — migrates all secrets to Secret Manager, removes plaintext env vars
- **Rollback Planner** — documents rollback procedures for every service, integrates with monitoring

Handoff Protocol:
  Dockerfile + CI/CD + IaC pushed to Git branch `ai-factory/{project}/devops`.
  Trivy and Checkov scans must PASS before handoff.
  QA Eng receives deployment URL for smoke tests via Slack.
  SRE Ops receives infra manifest and scaling config.
