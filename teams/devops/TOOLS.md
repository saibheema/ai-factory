# DevOps Team — TOOLS

Container & Build:
- **Git** (push): Dockerfile, CI/CD YAML, IaC to project branch
- **GitHub API**: Open PRs for infra changes with rollback plan
- **Docker**: Build + push images to GCR/Artifact Registry
- **GCS**: Store build artifacts and IaC state

Infrastructure:
- **Terraform**: Provision Cloud Run, VPC, IAM, Secret Manager, Cloud Armor
- **kubectl**: Manage Kubernetes deployments (if GKE target)
- **Helm**: Kubernetes chart management
- **Cloud Run**: Deploy and manage Cloud Run services (revision management, traffic splits)

Security Scanning:
- **Trivy**: CVE scan on container images + IaC misconfiguration
- **Checkov**: Terraform + Kubernetes + Dockerfile policy checks
- **Gitleaks**: Secret scanning on all config files

Testing:
- **Sandbox**: Run containers in isolated test environment pre-deploy

Tracking:
- **Plane**: Infra issue per service, linked to Sol Arch ADR decisions

Notifications:
- **Slack**: #devops channel — deployment complete with service URL + image digest
- **Notification**: Stage-complete broadcast to QA Eng and SRE Ops
