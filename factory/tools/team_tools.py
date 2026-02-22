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
        tools=["google_docs", "tavily_search", "mermaid", "plane", "notification"],
        artifacts=["PRD (Product Requirements Doc)", "Feature Roadmap", "Milestone Plan"],
        output_target="google_docs",
        description="Writes PRDs and roadmaps as Google Docs, researches market via Tavily, tracks epics in Plane",
    ),
    "biz_analysis": TeamToolConfig(
        team="biz_analysis",
        display_name="Business Analysis",
        tools=["google_docs", "google_sheets", "tavily_search", "plane", "notification"],
        artifacts=["BRD (Business Requirements Doc)", "Acceptance Criteria Matrix", "Stakeholder Analysis"],
        output_target="google_docs",
        secondary_target="google_sheets",
        description="Writes BRD in Google Docs, acceptance criteria in Sheets, issues filed in Plane",
    ),

    # ─── Architecture & Design (→ Google Docs + Diagrams) ───
    "solution_arch": TeamToolConfig(
        team="solution_arch",
        display_name="Solution Architecture",
        tools=["google_docs", "mermaid", "tavily_search", "notification"],
        artifacts=["Architecture Decision Record (ADR)", "System Architecture Doc", "C4 Diagrams", "Tech Stack Analysis"],
        output_target="google_docs",
        description="Writes ADRs and arch docs in Google Docs, generates Mermaid C4/sequence diagrams",
    ),
    "api_design": TeamToolConfig(
        team="api_design",
        display_name="API Design",
        tools=["git", "mermaid", "google_docs", "spectral", "notification"],
        artifacts=["OpenAPI Spec (YAML)", "API Sequence Diagrams", "Contract Documentation", "Spectral Lint Report"],
        output_target="git",
        secondary_target="google_docs",
        description="Pushes OpenAPI YAML to Git, lints with Spectral, writes API contract docs in Google Docs",
    ),
    "ux_ui": TeamToolConfig(
        team="ux_ui",
        display_name="UX / UI Design",
        tools=["google_docs", "mermaid", "notification"],
        artifacts=["UX Flow Document", "Wireframe Specifications", "Component Design Tokens"],
        output_target="google_docs",
        description="Writes UX flow specs and wireframe docs in Google Docs with Mermaid flows",
    ),

    # ─── Engineering (→ Git) ───
    "frontend_eng": TeamToolConfig(
        team="frontend_eng",
        display_name="Frontend Engineering",
        tools=["git", "gcs", "github_api", "sandbox", "notification"],
        artifacts=["React/Vue Components", "State Management", "UI Tests", "package.json"],
        output_target="git",
        secondary_target="gcs",
        description="Pushes frontend code to Git, creates PRs via GitHub API, validates in sandbox",
    ),
    "backend_eng": TeamToolConfig(
        team="backend_eng",
        display_name="Backend Engineering",
        tools=["git", "gcs", "github_api", "ruff", "pytest", "sandbox", "notification"],
        artifacts=["API Endpoints", "Service Layer", "Unit Tests", "requirements.txt"],
        output_target="git",
        secondary_target="gcs",
        description="Pushes backend code to Git, lints with Ruff, tests with pytest, runs in sandbox",
    ),
    "database_eng": TeamToolConfig(
        team="database_eng",
        display_name="Database Engineering",
        tools=["git", "gcs", "google_docs", "github_api", "notification"],
        artifacts=["DDL Schema", "Migration Scripts", "ER Diagram", "Data Dictionary"],
        output_target="git",
        secondary_target="google_docs",
        description="Pushes DDL/migrations to Git, creates PRs via GitHub API, data dictionary in Docs",
    ),
    "data_eng": TeamToolConfig(
        team="data_eng",
        display_name="Data Engineering",
        tools=["git", "gcs", "github_api", "notification"],
        artifacts=["ETL Pipeline Config", "Data Transformation Scripts", "Pipeline DAG"],
        output_target="git",
        secondary_target="gcs",
        description="Pushes ETL scripts and pipeline configs to Git, creates PRs via GitHub API",
    ),
    "ml_eng": TeamToolConfig(
        team="ml_eng",
        display_name="ML Engineering",
        tools=["git", "gcs", "tavily_search", "mlflow", "sandbox", "github_api", "notification"],
        artifacts=["Model Training Script", "Evaluation Config", "Model Card", "MLflow Experiment Run"],
        output_target="git",
        secondary_target="gcs",
        description="Pushes ML code to Git, logs experiments in MLflow, researches OSS models via Tavily",
    ),

    # ─── Security & Compliance (→ Google Docs/Sheets) ───
    "security_eng": TeamToolConfig(
        team="security_eng",
        display_name="Security Engineering",
        tools=["google_docs", "google_sheets", "tavily_search", "semgrep", "trivy", "notification"],
        artifacts=["Threat Model (STRIDE)", "SAST Report (Semgrep)", "CVE Scan (Trivy)", "Security Controls Matrix"],
        output_target="google_docs",
        secondary_target="google_sheets",
        description="SAST via Semgrep, CVE scan via Trivy, writes threat model and controls in Docs/Sheets",
    ),
    "compliance": TeamToolConfig(
        team="compliance",
        display_name="Compliance",
        tools=["google_docs", "google_sheets", "notification"],
        artifacts=["Compliance Checklist", "Audit Trail Report", "Policy Mapping"],
        output_target="google_docs",
        secondary_target="google_sheets",
        description="Writes compliance docs in Google Docs, audit checklists in Sheets",
    ),

    # ─── DevOps & Infra (→ Git) ───
    "devops": TeamToolConfig(
        team="devops",
        display_name="DevOps",
        tools=["git", "gcs", "github_api", "trivy", "sandbox", "notification"],
        artifacts=["Dockerfile", "CI/CD Pipeline (GitHub Actions)", "IaC (Terraform/CloudFormation)", "docker-compose.yaml", "Trivy IaC Scan Report"],
        output_target="git",
        secondary_target="gcs",
        description="Pushes Dockerfiles, CI/CD, IaC to Git; scans containers/IaC with Trivy",
    ),

    # ─── QA (→ Google Sheets + Git) ───
    "qa_eng": TeamToolConfig(
        team="qa_eng",
        display_name="QA Engineering",
        tools=["google_sheets", "git", "gcs", "pytest", "sandbox", "plane", "notification"],
        artifacts=["Test Plan & Cases (Sheet)", "Test Automation Code", "Coverage Report", "pytest JSON Report"],
        output_target="google_sheets",
        secondary_target="git",
        description="Writes test plan in Sheets, runs pytest in sandbox, tracks test issues in Plane",
    ),

    # ─── Operations (→ Google Docs + Git) ───
    "sre_ops": TeamToolConfig(
        team="sre_ops",
        display_name="SRE / Operations",
        tools=["google_docs", "git", "github_api", "trivy", "notification"],
        artifacts=["Runbook", "SLO/SLI Definitions", "Alert Rules (YAML)", "Grafana Dashboard JSON"],
        output_target="google_docs",
        secondary_target="git",
        description="Writes runbooks in Google Docs, pushes alert configs to Git, scans runtime images with Trivy",
    ),

    # ─── Documentation (→ Google Docs) ───
    "docs_team": TeamToolConfig(
        team="docs_team",
        display_name="Documentation",
        tools=["google_docs", "mermaid", "git", "notification"],
        artifacts=["User Guide", "API Reference", "Changelog", "Getting Started Guide"],
        output_target="google_docs",
        secondary_target="git",
        description="Writes all documentation in Google Docs with Mermaid diagrams, pushes Markdown to Git",
    ),

    # ─── Feature Delivery (→ Google Sheets) ───
    "feature_eng": TeamToolConfig(
        team="feature_eng",
        display_name="Feature Engineering",
        tools=["google_sheets", "google_docs", "plane", "notification"],
        artifacts=["Feature Tracker (Sheet)", "Story Cards", "Backlog Prioritization", "Plane Issues"],
        output_target="google_sheets",
        secondary_target="google_docs",
        description="Manages feature tracker in Sheets, story cards in Docs, creates Plane issues per story",
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
