class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, str] = {}

    def register(self, name: str, description: str) -> None:
        self._tools[name] = description

    def list_tools(self) -> dict[str, str]:
        return dict(self._tools)


def phase1_default_tools() -> ToolRegistry:
    registry = ToolRegistry()
    # ── Code & Git ────────────────────────────────────────────────────────────
    registry.register("github_api", "Repository, PR and issue management (GitHub REST API)")
    registry.register("git", "Clone, branch, commit and push files to Git")
    registry.register("gcs", "Upload artifacts to Google Cloud Storage")
    # ── Code Quality ──────────────────────────────────────────────────────────
    registry.register("sandbox", "Execute code/tests in isolated subprocess (timeout enforced)")
    registry.register("ruff", "Python linting via Ruff CLI (open source, fast)")
    registry.register("pytest", "Automated tests via pytest + pytest-json-report")
    # ── Research & Diagramming ────────────────────────────────────────────────
    registry.register("tavily_search", "Web research via Tavily API")
    registry.register("mermaid", "Architecture diagram generation (Mermaid.js)")
    # ── Google Workspace ──────────────────────────────────────────────────────
    registry.register("google_docs", "Create and write Google Documents")
    registry.register("google_sheets", "Create structured Google Spreadsheets")
    # ── Project Management (open source JIRA alternative) ────────────────────
    registry.register("plane", "Issue tracking, sprints, and backlog via Plane (MIT, self-hosted)")
    # ── API Design ───────────────────────────────────────────────────────────
    registry.register("spectral", "OpenAPI/AsyncAPI spec linting via Spectral CLI (Apache-2.0)")
    # ── Security & Compliance ─────────────────────────────────────────────────
    registry.register("semgrep", "SAST security scanning via Semgrep OSS (LGPL-2.1)")
    registry.register("trivy", "Container, filesystem, IaC, and secret scanning via Trivy (Apache-2.0)")
    # ── ML Ops ────────────────────────────────────────────────────────────────
    registry.register("mlflow", "ML experiment tracking and model registry via MLflow (Apache-2.0)")
    # ── Notifications ─────────────────────────────────────────────────────────
    registry.register("notification", "Team handoff and stage-complete alerts via ntfy/Slack/webhook")
    return registry


def all_tools() -> ToolRegistry:
    """Return the full registry with every tool available across all teams."""
    registry = phase1_default_tools()

    # ── Infrastructure & DevOps ───────────────────────────────────────────────
    registry.register("kubectl", "Kubernetes pod/deployment/log management via kubectl CLI")
    registry.register("helm", "Helm chart install, upgrade, rollback, and status")
    registry.register("terraform", "IaC plan/apply/validate with embedded Checkov IaC scan")
    registry.register("docker", "Container image build, push, inspect, run, and Trivy scan")
    registry.register("cloudrun", "Google Cloud Run service deploy, describe, and log retrieval")

    # ── Load Testing ─────────────────────────────────────────────────────────
    registry.register("k6", "HTTP load testing and SLO validation via k6 (Grafana OSS)")

    # ── Data & Storage ────────────────────────────────────────────────────────
    registry.register("sql", "PostgreSQL query execution, DDL, and schema inspection")
    registry.register("bigquery", "Google BigQuery query execution, schema inspection, and cost estimation")
    registry.register("redis", "Redis key inspection, info, flush, and health check")
    registry.register("csv", "CSV parse, validate, transform, describe, and JSON export")

    # ── Collaboration ─────────────────────────────────────────────────────────
    registry.register("slack", "Rich Slack messaging: blocks, alerts, file upload, channel creation")
    registry.register("confluence", "Confluence wiki page create, update, and upsert (Storage Format)")
    registry.register("jira", "Jira issue create, search (JQL), transition, and comment (REST API v3)")

    # ── Security ─────────────────────────────────────────────────────────────
    registry.register("bandit", "Python SAST via Bandit — detects injection, weak crypto, shell escape flaws")
    registry.register("gitleaks", "Secret and credential scanning in Git history via Gitleaks")
    registry.register("checkov", "Standalone IaC security scanner (Terraform, K8s, Dockerfile, GHA)")

    # ── Code Quality ──────────────────────────────────────────────────────────
    registry.register("mypy", "Python static type checking via mypy")
    registry.register("black", "Opinionated Python code formatting and diff reporting via Black")

    # ── Testing ───────────────────────────────────────────────────────────────
    registry.register("playwright", "Headless browser E2E tests, screenshots, accessibility audits")

    # ── AI / ML ───────────────────────────────────────────────────────────────
    registry.register("huggingface", "HuggingFace Hub model/dataset search, model cards, and file listing")
    registry.register("openai", "OpenAI chat completions, embeddings, and structured extraction")

    # ── Research & Scraping ───────────────────────────────────────────────────
    registry.register("wikipedia", "Wikipedia article search, summaries, and related article discovery")
    registry.register("firecrawl", "Web scraping and site crawling via Firecrawl API (LLM-ready markdown)")

    # ── Incident Management ───────────────────────────────────────────────────
    registry.register("pagerduty", "PagerDuty incident create, acknowledge, resolve, and timeline notes")

    return registry
