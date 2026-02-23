"""Definitive Team → Tool mapping for AI Factory.

Each team has:
  - tools: list of tool keys they execute during a pipeline run
  - artifacts: what they produce and where it goes
  - output_target: "google_docs" | "google_sheets" | "git" | "gcs"

This is the single source of truth for which tools each SDLC team uses.
"""

from dataclasses import dataclass, field


@dataclass
class TeamToolConfig:
    """Configuration for one team's tool usage."""

    team: str
    display_name: str
    tools: list[str]
    artifacts: list[str]
    output_target: str  # primary: google_docs | google_sheets | git | gcs
    secondary_target: str = ""  # optional secondary output
    description: str = ""


# ═══════════════════════════════════════════════════════════
#  THE DEFINITIVE MAPPING — 100% confidence
# ═══════════════════════════════════════════════════════════

TEAM_TOOLS: dict[str, TeamToolConfig] = {
    # ─── Strategy & Planning (→ Google Docs) ───
    "product_mgmt": TeamToolConfig(
        team="product_mgmt",
        display_name="Product Management",
        tools=[
            "google_docs", "tavily_search", "mermaid", "plane",
            "jira", "wikipedia", "firecrawl", "slack", "notification",
        ],
        artifacts=["PRD (Product Requirements Doc)", "Feature Roadmap", "Milestone Plan"],
        output_target="google_docs",
        description=(
            "Writes PRDs and roadmaps as Google Docs, researches market via Tavily/Firecrawl/Wikipedia, "
            "tracks epics in Plane and Jira, sends stage summaries to Slack"
        ),
    ),
    "biz_analysis": TeamToolConfig(
        team="biz_analysis",
        display_name="Business Analysis",
        tools=[
            "google_docs", "google_sheets", "tavily_search", "plane",
            "jira", "confluence", "wikipedia", "firecrawl", "csv", "slack", "notification",
        ],
        artifacts=["BRD (Business Requirements Doc)", "Acceptance Criteria Matrix", "Stakeholder Analysis"],
        output_target="google_docs",
        secondary_target="google_sheets",
        description=(
            "Writes BRD in Google Docs, acceptance criteria in Sheets, publishes to Confluence, "
            "imports/analyses CSV data, researches via Firecrawl/Wikipedia, tracks in Plane & Jira"
        ),
    ),

    # ─── Architecture & Design (→ Google Docs + Diagrams) ───
    "solution_arch": TeamToolConfig(
        team="solution_arch",
        display_name="Solution Architecture",
        tools=[
            "google_docs", "google_sheets", "mermaid", "tavily_search", "plane",
            "confluence", "openai", "wikipedia", "firecrawl", "slack", "notification",
        ],
        artifacts=[
            "Architecture Decision Record (ADR)",
            "System Architecture Doc",
            "Tech Stack Decision Matrix (Sheet)",
            "C4 Context + Component Diagrams",
            "Tech Research Report",
            "Per-Team Handoff Notes",
        ],
        output_target="google_docs",
        secondary_target="google_sheets",
        description=(
            "Performs extensive research (5 Tavily queries + Firecrawl + Wikipedia) on UI stack, backend, "
            "cloud infra, security, and reference architectures. Writes ADR + per-team handoff notes in "
            "Google Docs + Confluence. Produces Tech Stack Decision Matrix in Sheets. "
            "Generates C4 context + component Mermaid diagrams. Uses OpenAI for tech spike analysis. "
            "Tracks ADRs in Plane. Notifies all teams via Slack with handoff instructions."
        ),
    ),
    "api_design": TeamToolConfig(
        team="api_design",
        display_name="API Design",
        tools=[
            "git", "mermaid", "google_docs", "spectral", "plane",
            "openai", "slack", "notification",
        ],
        artifacts=["OpenAPI Spec (YAML)", "API Sequence Diagrams", "Contract Documentation", "Spectral Lint Report"],
        output_target="git",
        secondary_target="google_docs",
        description=(
            "Pushes OpenAPI YAML to Git, lints with Spectral, writes API contract docs in Google Docs, "
            "uses OpenAI for spec generation/review, tracks API issues in Plane"
        ),
    ),
    "ux_ui": TeamToolConfig(
        team="ux_ui",
        display_name="UX / UI Design",
        tools=[
            "google_docs", "mermaid", "plane",
            "playwright", "firecrawl", "slack", "notification",
        ],
        artifacts=["UX Flow Document", "Wireframe Specifications", "Component Design Tokens"],
        output_target="google_docs",
        description=(
            "Writes UX flow specs and wireframe docs with Mermaid flows, runs Playwright accessibility audits, "
            "uses Firecrawl for competitive research, tracks UX work in Plane"
        ),
    ),

    # ─── Engineering (→ Git) ───
    "frontend_eng": TeamToolConfig(
        team="frontend_eng",
        display_name="Frontend Engineering",
        tools=[
            "git", "gcs", "github_api", "sandbox", "plane",
            "playwright", "docker", "black", "slack", "notification",
        ],
        artifacts=["React/Vue Components", "State Management", "UI Tests", "package.json", "E2E Test Suite"],
        output_target="git",
        secondary_target="gcs",
        description=(
            "Pushes frontend code to Git, creates PRs via GitHub API, runs Playwright E2E tests, "
            "formats Python helpers with Black, builds Docker images, tracks stories in Plane"
        ),
    ),
    "backend_eng": TeamToolConfig(
        team="backend_eng",
        display_name="Backend Engineering",
        tools=[
            "git", "gcs", "github_api", "ruff", "pytest", "sandbox", "plane",
            "sql", "docker", "black", "mypy", "redis", "slack", "notification",
        ],
        artifacts=["API Endpoints", "Service Layer", "Unit Tests", "requirements.txt"],
        output_target="git",
        secondary_target="gcs",
        description=(
            "Pushes backend code to Git, lints with Ruff/Black/mypy, tests with pytest, "
            "queries Postgres with sql tool, inspects Redis cache, builds Docker images, tracks in Plane"
        ),
    ),
    "database_eng": TeamToolConfig(
        team="database_eng",
        display_name="Database Engineering",
        tools=[
            "git", "gcs", "google_docs", "github_api", "plane",
            "sql", "bigquery", "csv", "slack", "notification",
        ],
        artifacts=["DDL Schema", "Migration Scripts", "ER Diagram", "Data Dictionary"],
        output_target="git",
        secondary_target="google_docs",
        description=(
            "Pushes DDL/migrations to Git, executes SQL schema validation, queries BigQuery, "
            "imports/validates CSV datasets, data dictionary in Docs, tracks schema issues in Plane"
        ),
    ),
    "data_eng": TeamToolConfig(
        team="data_eng",
        display_name="Data Engineering",
        tools=[
            "git", "gcs", "github_api", "plane",
            "sql", "bigquery", "csv", "mypy", "slack", "notification",
        ],
        artifacts=["ETL Pipeline Config", "Data Transformation Scripts", "Pipeline DAG"],
        output_target="git",
        secondary_target="gcs",
        description=(
            "Pushes ETL scripts to Git, executes Postgres/BigQuery queries, validates CSV schemas, "
            "type-checks Python with mypy, tracks pipeline issues in Plane"
        ),
    ),
    "ml_eng": TeamToolConfig(
        team="ml_eng",
        display_name="ML Engineering",
        tools=[
            "git", "gcs", "tavily_search", "mlflow", "sandbox", "github_api", "plane",
            "bigquery", "huggingface", "openai", "mypy", "slack", "notification",
        ],
        artifacts=["Model Training Script", "Evaluation Config", "Model Card", "MLflow Experiment Run"],
        output_target="git",
        secondary_target="gcs",
        description=(
            "Pushes ML code to Git, logs experiments in MLflow, discovers models on HuggingFace Hub, "
            "queries BigQuery for training data, uses OpenAI for LLM tasks, type-checks with mypy, tracks in Plane"
        ),
    ),

    # ─── Security & Compliance (→ Google Docs/Sheets) ───
    "security_eng": TeamToolConfig(
        team="security_eng",
        display_name="Security Engineering",
        tools=[
            "google_docs", "google_sheets", "tavily_search", "semgrep", "trivy", "plane",
            "bandit", "gitleaks", "checkov", "slack", "notification",
        ],
        artifacts=["Threat Model (STRIDE)", "SAST Report", "CVE Scan", "IaC Scan Report", "Secret Scan Report", "Security Controls Matrix"],
        output_target="google_docs",
        secondary_target="google_sheets",
        description=(
            "SAST via Semgrep + Bandit, CVE scan via Trivy, IaC scan via Checkov, "
            "secret scanning via Gitleaks, writes threat model and controls in Docs/Sheets, alerts via Slack"
        ),
    ),
    "compliance": TeamToolConfig(
        team="compliance",
        display_name="Compliance",
        tools=[
            "google_docs", "google_sheets", "plane",
            "confluence", "slack", "notification",
        ],
        artifacts=["Compliance Checklist", "Audit Trail Report", "Policy Mapping"],
        output_target="google_docs",
        secondary_target="google_sheets",
        description=(
            "Writes compliance docs in Google Docs and Confluence, audit checklists in Sheets, "
            "tracks compliance items in Plane, notifies via Slack"
        ),
    ),

    # ─── DevOps & Infra (→ Git) ───
    "devops": TeamToolConfig(
        team="devops",
        display_name="DevOps",
        tools=[
            "git", "gcs", "github_api", "trivy", "sandbox", "plane",
            "kubectl", "helm", "terraform", "docker", "checkov", "cloudrun",
            "gitleaks", "slack", "notification",
        ],
        artifacts=["Dockerfile", "CI/CD Pipeline (GitHub Actions)", "IaC (Terraform)", "docker-compose.yaml", "Helm Chart", "Trivy/Checkov Scan Reports"],
        output_target="git",
        secondary_target="gcs",
        description=(
            "Pushes Dockerfiles, CI/CD, IaC to Git; manages K8s via kubectl/helm; "
            "runs Terraform plan/apply; scans containers/IaC with Trivy+Checkov; "
            "deploys to Cloud Run; detects secrets with Gitleaks; alerts via Slack"
        ),
    ),

    # ─── QA (→ Google Sheets + Git) ───
    "qa_eng": TeamToolConfig(
        team="qa_eng",
        display_name="QA Engineering",
        tools=[
            "google_sheets", "git", "gcs", "pytest", "sandbox", "plane",
            "k6", "playwright", "sql", "csv", "slack", "notification",
        ],
        artifacts=["Test Plan & Cases (Sheet)", "Test Automation Code", "Coverage Report", "Load Test Report", "E2E Test Suite"],
        output_target="google_sheets",
        secondary_target="git",
        description=(
            "Writes test plan in Sheets, runs pytest in sandbox, executes k6 load tests, "
            "runs Playwright E2E + accessibility tests, validates SQL schemas, imports CSV test data, "
            "tracks test issues in Plane, reports to Slack"
        ),
    ),

    # ─── Operations (→ Google Docs + Git) ───
    "sre_ops": TeamToolConfig(
        team="sre_ops",
        display_name="SRE / Operations",
        tools=[
            "google_docs", "git", "github_api", "trivy", "plane",
            "kubectl", "helm", "k6", "redis", "cloudrun", "pagerduty",
            "slack", "notification",
        ],
        artifacts=["Runbook", "SLO/SLI Definitions", "Alert Rules (YAML)", "Grafana Dashboard JSON", "Load Test Report"],
        output_target="google_docs",
        secondary_target="git",
        description=(
            "Writes runbooks in Google Docs, manages K8s with kubectl/helm, validates SLOs with k6 load tests, "
            "inspects Redis cache health, manages Cloud Run services, creates PagerDuty incidents, "
            "scans runtime images with Trivy, alerts via Slack"
        ),
    ),

    # ─── Documentation (→ Google Docs) ───
    "docs_team": TeamToolConfig(
        team="docs_team",
        display_name="Documentation",
        tools=[
            "google_docs", "mermaid", "git", "plane",
            "confluence", "wikipedia", "slack", "notification",
        ],
        artifacts=["User Guide", "API Reference", "Changelog", "Getting Started Guide"],
        output_target="google_docs",
        secondary_target="git",
        description=(
            "Writes all documentation in Google Docs and Confluence with Mermaid diagrams, "
            "pushes Markdown to Git, enriches content via Wikipedia, tracks doc issues in Plane"
        ),
    ),

    # ─── Feature Delivery (→ Google Sheets) ───
    "feature_eng": TeamToolConfig(
        team="feature_eng",
        display_name="Feature Engineering",
        tools=[
            "google_sheets", "google_docs", "plane",
            "jira", "slack", "notification",
        ],
        artifacts=["Feature Tracker (Sheet)", "Story Cards", "Backlog Prioritization"],
        output_target="google_sheets",
        secondary_target="google_docs",
        description=(
            "Manages feature tracker in Sheets, story cards in Docs, creates Plane + Jira issues per story, "
            "notifies stakeholders via Slack"
        ),
    ),
}


def get_team_tools(team: str) -> TeamToolConfig | None:
    """Get the tool config for a team."""
    return TEAM_TOOLS.get(team)


def get_all_team_tools() -> dict[str, TeamToolConfig]:
    """Get the full team→tools mapping."""
    return dict(TEAM_TOOLS)


def get_team_tool_summary() -> list[dict]:
    """Get a summary list suitable for API responses."""
    return [
        {
            "team": cfg.team,
            "display_name": cfg.display_name,
            "tools": cfg.tools,
            "artifacts": cfg.artifacts,
            "output_target": cfg.output_target,
            "secondary_target": cfg.secondary_target,
            "description": cfg.description,
        }
        for cfg in TEAM_TOOLS.values()
    ]
