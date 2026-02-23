# Security Engineering Team — AGENTS

Operatives:
- **Threat Modeler** — produces STRIDE analysis for all system components and data flows
- **SAST Analyst** — runs Semgrep and Bandit on all generated code, triages findings
- **IaC Security Scanner** — runs Checkov and Trivy on Dockerfiles, Terraform, Helm charts
- **Secret Scanner** — runs Gitleaks on all code artifacts, flags and blocks any detected secrets
- **Auth Verifier** — checks that auth mechanism chosen by Sol Arch ADR is correctly implemented
- **Security Controls Author** — writes the Security Controls Matrix (Google Sheets)
- **Remediation Guide Author** — for each finding, writes specific remediation code/config
- **Compliance Liaison** — pre-validates controls against SOC 2 / OWASP / PCI-DSS requirements

Handoff Protocol:
  Security Controls Matrix published to Google Sheets.
  SAST/IaC/Secret scan reports attached to Plane issue.
  Compliance team receives controls matrix via Slack for audit evidence.
