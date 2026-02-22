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
    return phase1_default_tools()
