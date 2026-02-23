# Security Engineering Team — TOOLS

SAST / Code Scanning:
- **Semgrep**: Static analysis across all generated code (Python, JS/TS, Go, Dockerfile)
- **Bandit**: Python-specific SAST for common security issues
- **Gitleaks**: Secret scanning — API keys, passwords, tokens in code and config files

IaC Scanning:
- **Checkov**: Terraform, Kubernetes manifests, Dockerfile policy checks
- **Trivy**: Container image CVE scan + IaC misconfiguration detection

Research:
- **Tavily Search**: OWASP top 10, CVE advisories, security best practices for chosen stack

Documentation:
- **Google Docs**: Threat Model (STRIDE analysis with mitigations)
- **Google Sheets**: Security Controls Matrix (Control ID, Category, Status, Risk, Owner)

Tracking:
- **Plane**: Security finding issue per HIGH/CRITICAL, linked to originating team's story

Notifications:
- **Slack**: #security channel — scan results with finding counts (CRITICAL/HIGH/MEDIUM)
- **Notification**: Stage-complete broadcast to Compliance team
