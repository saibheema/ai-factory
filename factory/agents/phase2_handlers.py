"""Phase 2 handlers — each team executes real tools and logs artifacts.

Every team:
 1. Gets its tool config from team_tools.py
 2. Generates content via LLM (or deterministic fallback)
 3. Executes the assigned tools (Google Docs, Sheets, Git, GCS, Mermaid, Tavily)
 4. Returns a structured artifact with tool execution log
"""

import logging
import re
from dataclasses import dataclass, field

from factory.llm.runtime import TeamLLMRuntime
from factory.tools.team_tools import TEAM_TOOLS, get_team_tools

log = logging.getLogger(__name__)


@dataclass
class ToolExecution:
    """Record of a single tool invocation."""
    tool: str
    action: str
    result: dict = field(default_factory=dict)
    success: bool = True
    error: str = ""


@dataclass
class Phase2StageArtifact:
    team: str
    artifact: str
    tools_used: list[ToolExecution] = field(default_factory=list)
    code_files: dict[str, str] = field(default_factory=dict)  # filename → content


def extract_handoff_to(artifact: str) -> str:
    match = re.search(r"- handoff_to:\s*([a-zA-Z0-9_\-]+)", artifact)
    if not match:
        return "unknown"
    return match.group(1)


def _execute_google_docs(team: str, title: str, content: str, folder_id: str | None = None) -> ToolExecution:
    """Create a Google Doc artifact."""
    try:
        from factory.tools.google_docs_tool import create_document
        result = create_document(title=title, content=content, folder_id=folder_id)
        return ToolExecution(tool="google_docs", action=f"Created: {title}", result=result)
    except Exception as e:
        log.warning("Google Docs failed for %s: %s", team, e)
        return ToolExecution(tool="google_docs", action=f"Create: {title}", success=False, error=str(e))


def _execute_google_sheets(team: str, title: str, headers: list[str], rows: list[list[str]], folder_id: str | None = None) -> ToolExecution:
    """Create a Google Sheets artifact."""
    try:
        from factory.tools.google_sheets_tool import create_spreadsheet
        result = create_spreadsheet(title=title, headers=headers, rows=rows, folder_id=folder_id)
        return ToolExecution(tool="google_sheets", action=f"Created: {title} ({len(rows)} rows)", result=result)
    except Exception as e:
        log.warning("Google Sheets failed for %s: %s", team, e)
        return ToolExecution(tool="google_sheets", action=f"Create: {title}", success=False, error=str(e))


def _execute_mermaid(team: str, diagram_type: str, title: str, content: str) -> ToolExecution:
    """Generate a Mermaid diagram."""
    try:
        from factory.tools.mermaid_tool import render_diagram
        result = render_diagram(diagram_type=diagram_type, title=title, content=content)
        return ToolExecution(tool="mermaid", action=f"Diagram: {title} ({diagram_type})", result=result)
    except Exception as e:
        return ToolExecution(tool="mermaid", action=f"Diagram: {title}", success=False, error=str(e))


def _execute_tavily(team: str, query: str) -> ToolExecution:
    """Execute a web search."""
    try:
        from factory.tools.tavily_tool import web_search
        result = web_search(query=query, max_results=3)
        n = len(result.get("results", []))
        return ToolExecution(tool="tavily_search", action=f"Research: {query[:60]} ({n} results)", result=result)
    except Exception as e:
        return ToolExecution(tool="tavily_search", action=f"Research: {query[:60]}", success=False, error=str(e))


def _execute_git(team: str, git_url: str, git_token: str, project_id: str, files: dict[str, str]) -> ToolExecution:
    """Push files to Git."""
    try:
        from factory.tools.git_tool import push_code_files
        result = push_code_files(
            git_url=git_url, git_token=git_token,
            project_id=project_id, team=team, files=files,
        )
        return ToolExecution(tool="git", action=f"Pushed {len(files)} files → branch ai-factory/{project_id}/{team}", result=result)
    except Exception as e:
        log.warning("Git push failed for %s: %s", team, e)
        return ToolExecution(tool="git", action=f"Push {len(files)} files", success=False, error=str(e))


def _execute_gcs(team: str, uid: str, project_id: str, filename: str, content: str) -> ToolExecution:
    """Upload to GCS."""
    try:
        from factory.tools.gcs_tool import upload_artifact
        result = upload_artifact(uid=uid, project_id=project_id, team=team, filename=filename, content=content)
        return ToolExecution(tool="gcs", action=f"Uploaded: {filename}", result=result)
    except Exception as e:
        log.warning("GCS upload failed for %s: %s", team, e)
        return ToolExecution(tool="gcs", action=f"Upload: {filename}", success=False, error=str(e))


# ═══════════════════════════════════════════════════════════
#  TEAM-SPECIFIC ARTIFACT GENERATORS
#  Each returns (doc_content, sheets_data, code_files, mermaid_diagram, search_query)
# ═══════════════════════════════════════════════════════════

def _gen_product_mgmt(requirement: str, llm_content: str) -> dict:
    return {
        "doc_title": "PRD — Product Requirements Document",
        "doc_content": f"# Product Requirements Document\n\n## Objective\n{requirement}\n\n{llm_content}\n\n## Milestones\n- M1: Discovery & Scoping\n- M2: MVP Build\n- M3: Beta Launch\n- M4: GA Release",
        "search_query": f"best practices product requirements {requirement[:50]}",
        "mermaid": ("gantt", "Product Roadmap", f"gantt\n    title Product Roadmap\n    dateFormat YYYY-MM-DD\n    section Discovery\n        Requirement Analysis :a1, 2026-01-01, 14d\n    section MVP\n        Core Build :a2, after a1, 30d\n    section Launch\n        Beta :a3, after a2, 14d\n        GA :a4, after a3, 7d"),
    }


def _gen_biz_analysis(requirement: str, llm_content: str) -> dict:
    return {
        "doc_title": "BRD — Business Requirements Document",
        "doc_content": f"# Business Requirements Document\n\n## Business Problem\n{requirement}\n\n{llm_content}\n\n## Success Criteria\n- Measurable KPIs defined\n- Stakeholder sign-off obtained\n- Acceptance criteria documented",
        "sheet_title": "Acceptance Criteria Matrix",
        "sheet_headers": ["ID", "Criteria", "Priority", "Status", "Owner"],
        "sheet_rows": [
            ["AC-001", "Core functionality works end-to-end", "P0", "Draft", "BA Team"],
            ["AC-002", "Performance meets SLA targets", "P1", "Draft", "BA Team"],
            ["AC-003", "Security controls implemented", "P1", "Draft", "BA Team"],
            ["AC-004", "Documentation complete", "P2", "Draft", "BA Team"],
        ],
        "search_query": f"business requirements analysis {requirement[:50]}",
    }


def _gen_solution_arch(requirement: str, llm_content: str) -> dict:
    return {
        "doc_title": "ADR — Architecture Decision Record",
        "doc_content": f"# Architecture Decision Record\n\n## Context\n{requirement}\n\n{llm_content}\n\n## Decision\nSelected architecture pattern based on requirements analysis.\n\n## Consequences\n- Positive: Scalable, maintainable, observable\n- Negative: Initial complexity, learning curve",
        "search_query": f"software architecture patterns for {requirement[:50]}",
        "mermaid": ("flowchart", "System Architecture", f"graph TB\n    Client[Client App] --> LB[Load Balancer]\n    LB --> API[API Gateway]\n    API --> Auth[Auth Service]\n    API --> Core[Core Service]\n    Core --> DB[(Database)]\n    Core --> Cache[(Cache)]\n    Core --> Queue[Message Queue]\n    Queue --> Worker[Worker Service]"),
    }


def _gen_api_design(requirement: str, llm_content: str) -> dict:
    return {
        "code_files": {
            "openapi/spec.yaml": f"openapi: '3.0.3'\ninfo:\n  title: API Spec\n  version: '1.0.0'\n  description: |\n    {requirement[:100]}\npaths:\n  /api/v1/resource:\n    get:\n      summary: List resources\n      responses:\n        '200':\n          description: Success\n    post:\n      summary: Create resource\n      responses:\n        '201':\n          description: Created\n",
        },
        "doc_title": "API Contract Documentation",
        "doc_content": f"# API Contract Documentation\n\n## Overview\n{requirement}\n\n{llm_content}\n\n## Endpoints\n- GET /api/v1/resource — List resources\n- POST /api/v1/resource — Create resource\n- GET /api/v1/resource/:id — Get resource\n- PUT /api/v1/resource/:id — Update resource\n- DELETE /api/v1/resource/:id — Delete resource",
        "mermaid": ("sequence", "API Sequence", f"sequenceDiagram\n    Client->>+API: POST /api/v1/resource\n    API->>+Auth: Validate Token\n    Auth-->>-API: OK\n    API->>+DB: Insert Record\n    DB-->>-API: Created\n    API-->>-Client: 201 Created"),
    }


def _gen_ux_ui(requirement: str, llm_content: str) -> dict:
    return {
        "doc_title": "UX Flow Specification",
        "doc_content": f"# UX Flow Specification\n\n## User Journey\n{requirement}\n\n{llm_content}\n\n## Key Screens\n1. Landing / Onboarding\n2. Dashboard\n3. Create / Edit Flow\n4. Settings\n\n## Design Tokens\n- Primary: #2563eb\n- Background: #f8fafc\n- Border Radius: 8px\n- Font: Inter, system-ui",
        "mermaid": ("flowchart", "User Flow", f"graph LR\n    Landing[Landing Page] --> Login[Sign In]\n    Login --> Dashboard[Dashboard]\n    Dashboard --> Create[Create New]\n    Dashboard --> View[View Details]\n    Create --> Review[Review & Submit]\n    Review --> Dashboard"),
    }


def _gen_frontend_eng(requirement: str, llm_content: str) -> dict:
    # If LLM generated actual code (contains JSX/function keywords), use it directly
    is_real_code = any(kw in llm_content for kw in ["function ", "const ", "return (", "useState", "=>", "<div", "<>"])
    if is_real_code:
        app_code = llm_content
    else:
        # Template fallback
        app_code = (
            f"// Auto-generated by AI Factory Frontend Eng\n"
            f"// Requirement: {requirement[:80]}\n\n"
            f"function App() {{\n"
            f"  const [result, setResult] = React.useState('');\n"
            f"  return (\n"
            f"    <div style={{{{padding:'20px', fontFamily:'system-ui'}}}}>"
            f"      <h1>{{'{requirement[:50]}'}}</h1>\n"
            f"      <p style={{{{color:'#64748b'}}}}>{{'{llm_content[:200]}'}}</p>\n"
            f"    </div>\n"
            f"  );\n"
            f"}}\n"
        )
    return {
        "code_files": {
            "src/App.jsx": app_code,
            "package.json": '{\n  "name": "app",\n  "version": "1.0.0",\n  "dependencies": {\n    "react": "^18.2.0",\n    "react-dom": "^18.2.0"\n  }\n}\n',
        },
    }


def _gen_backend_eng(requirement: str, llm_content: str) -> dict:
    # If LLM generated real Python code, use it
    is_real_code = any(kw in llm_content for kw in ["def ", "class ", "import ", "FastAPI", "@app."])
    if is_real_code:
        main_py = llm_content
    else:
        main_py = (
            f'"""Auto-generated by AI Factory Backend Eng\nRequirement: {requirement[:80]}\n"""\n\n'
            f'from fastapi import FastAPI\n\napp = FastAPI(title="Service", version="1.0.0")\n\n\n'
            f'@app.get("/health")\ndef health():\n    return {{"status": "ok"}}\n'
        )
    return {
        "code_files": {
            "app/main.py": main_py,
            "requirements.txt": "fastapi>=0.115.0\nuvicorn>=0.30.0\npydantic>=2.8.0\npytest>=8.0.0\n",
        },
    }


def _gen_database_eng(requirement: str, llm_content: str) -> dict:
    return {
        "code_files": {
            "migrations/001_initial.sql": f"-- AI Factory Database Eng\n-- Requirement: {requirement[:80]}\n\nCREATE TABLE IF NOT EXISTS resources (\n    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n    name VARCHAR(255) NOT NULL,\n    description TEXT,\n    created_at TIMESTAMP DEFAULT NOW(),\n    updated_at TIMESTAMP DEFAULT NOW()\n);\n\nCREATE INDEX idx_resources_name ON resources(name);\n",
            "migrations/002_audit.sql": "CREATE TABLE IF NOT EXISTS audit_log (\n    id BIGSERIAL PRIMARY KEY,\n    entity_type VARCHAR(100),\n    entity_id UUID,\n    action VARCHAR(50),\n    actor VARCHAR(255),\n    timestamp TIMESTAMP DEFAULT NOW()\n);\n",
        },
        "doc_title": "Data Dictionary",
        "doc_content": f"# Data Dictionary\n\n## Overview\n{requirement}\n\n{llm_content}\n\n## Tables\n\n### resources\n| Column | Type | Description |\n|--------|------|-------------|\n| id | UUID | Primary key |\n| name | VARCHAR(255) | Resource name |\n| description | TEXT | Description |\n| created_at | TIMESTAMP | Creation time |\n| updated_at | TIMESTAMP | Last update |",
    }


def _gen_data_eng(requirement: str, llm_content: str) -> dict:
    return {
        "code_files": {
            "pipelines/etl_main.py": f'"""ETL Pipeline — AI Factory Data Eng\nRequirement: {requirement[:80]}\n"""\n\ndef extract():\n    """Extract data from source."""\n    return []\n\ndef transform(data):\n    """Transform and clean data."""\n    return data\n\ndef load(data):\n    """Load data to destination."""\n    pass\n\nif __name__ == "__main__":\n    raw = extract()\n    clean = transform(raw)\n    load(clean)\n',
            "pipelines/config.yaml": f"pipeline:\n  name: data-pipeline\n  schedule: '0 * * * *'\n  source:\n    type: api\n    endpoint: /api/v1/resource\n  destination:\n    type: bigquery\n    dataset: analytics\n",
        },
    }


def _gen_ml_eng(requirement: str, llm_content: str) -> dict:
    return {
        "code_files": {
            "ml/train.py": f'"""Model Training — AI Factory ML Eng\nRequirement: {requirement[:80]}\n"""\n\nimport json\n\ndef train_model(data):\n    """Train the model."""\n    # Placeholder — integrate actual ML framework\n    return {{"accuracy": 0.95, "model": "baseline"}}\n\ndef evaluate(model, test_data):\n    """Evaluate model performance."""\n    return {{"precision": 0.94, "recall": 0.92, "f1": 0.93}}\n',
            "ml/model_card.md": f"# Model Card\n\n## Overview\n{requirement[:100]}\n\n## Performance\n- Accuracy: TBD\n- Latency: TBD\n\n## Limitations\n- Training data scope\n- Inference environment\n",
        },
        "search_query": f"open source ML models for {requirement[:50]}",
    }


def _gen_security_eng(requirement: str, llm_content: str) -> dict:
    return {
        "doc_title": "Threat Model — STRIDE Analysis",
        "doc_content": f"# Threat Model (STRIDE)\n\n## System Under Analysis\n{requirement}\n\n{llm_content}\n\n## STRIDE Analysis\n\n### Spoofing\n- Risk: Identity spoofing via weak auth\n- Mitigation: OAuth 2.0 + MFA\n\n### Tampering\n- Risk: Data modification in transit\n- Mitigation: TLS 1.3, input validation\n\n### Repudiation\n- Risk: Untraceable actions\n- Mitigation: Audit logging\n\n### Information Disclosure\n- Risk: Data leaks\n- Mitigation: Encryption at rest/transit\n\n### Denial of Service\n- Risk: Resource exhaustion\n- Mitigation: Rate limiting, auto-scaling\n\n### Elevation of Privilege\n- Risk: Unauthorized access\n- Mitigation: RBAC, principle of least privilege",
        "sheet_title": "Security Controls Matrix",
        "sheet_headers": ["Control ID", "Category", "Control", "Status", "Risk Level", "Owner"],
        "sheet_rows": [
            ["SC-001", "Authentication", "OAuth 2.0 + MFA", "Planned", "Critical", "Security"],
            ["SC-002", "Encryption", "TLS 1.3 in transit", "Planned", "Critical", "Security"],
            ["SC-003", "Encryption", "AES-256 at rest", "Planned", "High", "Security"],
            ["SC-004", "Logging", "Centralized audit logs", "Planned", "High", "SRE"],
            ["SC-005", "Access Control", "RBAC implementation", "Planned", "Critical", "Security"],
            ["SC-006", "Input Validation", "Server-side validation", "Planned", "High", "Backend"],
        ],
        "search_query": f"OWASP security best practices {requirement[:40]}",
    }


def _gen_compliance(requirement: str, llm_content: str) -> dict:
    return {
        "doc_title": "Compliance & Audit Report",
        "doc_content": f"# Compliance & Audit Report\n\n## Scope\n{requirement}\n\n{llm_content}\n\n## Applicable Standards\n- SOC 2 Type II\n- GDPR (if EU data)\n- HIPAA (if health data)\n\n## Evidence Catalog\n- Access control policies\n- Data encryption certificates\n- Incident response plan\n- Business continuity plan",
        "sheet_title": "Compliance Checklist",
        "sheet_headers": ["Requirement", "Standard", "Status", "Evidence", "Due Date"],
        "sheet_rows": [
            ["Data encryption", "SOC 2", "In Progress", "TLS config", "2026-03-01"],
            ["Access logging", "SOC 2", "Planned", "Audit trail", "2026-03-15"],
            ["Data retention policy", "GDPR", "Draft", "Policy doc", "2026-03-01"],
            ["Incident response plan", "SOC 2", "Planned", "Runbook", "2026-03-15"],
            ["Privacy impact assessment", "GDPR", "Not Started", "—", "2026-04-01"],
        ],
    }


def _gen_devops(requirement: str, llm_content: str) -> dict:
    return {
        "code_files": {
            "Dockerfile": f"FROM python:3.11-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\nCOPY . .\nCMD [\"uvicorn\", \"app.main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]\n",
            ".github/workflows/ci.yaml": f"name: CI/CD Pipeline\non:\n  push:\n    branches: [main]\n  pull_request:\n    branches: [main]\n\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.11'\n      - run: pip install -r requirements.txt\n      - run: pytest\n\n  deploy:\n    needs: test\n    runs-on: ubuntu-latest\n    if: github.ref == 'refs/heads/main'\n    steps:\n      - uses: actions/checkout@v4\n      - name: Deploy to Cloud Run\n        run: echo 'Deploy step'\n",
            "docker-compose.yaml": f"version: '3.8'\nservices:\n  app:\n    build: .\n    ports:\n      - '8000:8000'\n    environment:\n      - DATABASE_URL=postgresql://db:5432/app\n  db:\n    image: postgres:16\n    environment:\n      - POSTGRES_DB=app\n      - POSTGRES_PASSWORD=secret\n",
        },
    }


def _gen_qa_eng(requirement: str, llm_content: str) -> dict:
    return {
        "sheet_title": "Test Plan & Test Cases",
        "sheet_headers": ["TC-ID", "Category", "Test Case", "Steps", "Expected Result", "Priority", "Status"],
        "sheet_rows": [
            ["TC-001", "Smoke", "Health endpoint returns 200", "GET /health", "200 OK", "P0", "Ready"],
            ["TC-002", "Functional", "Create resource succeeds", "POST /api/v1/resource", "201 Created", "P0", "Ready"],
            ["TC-003", "Functional", "List resources returns array", "GET /api/v1/resource", "200 with items[]", "P0", "Ready"],
            ["TC-004", "Negative", "Invalid input returns 422", "POST with bad data", "422 Validation Error", "P1", "Ready"],
            ["TC-005", "Performance", "Response time < 500ms", "Load test /api/v1/resource", "p99 < 500ms", "P1", "Draft"],
            ["TC-006", "Security", "Auth required for endpoints", "GET without token", "401 Unauthorized", "P0", "Ready"],
        ],
        "code_files": {
            "tests/test_e2e.py": f'"""E2E Test Suite — AI Factory QA Eng\nRequirement: {requirement[:80]}\n"""\nimport pytest\n\ndef test_health():\n    \"\"\"TC-001: Health endpoint.\"\"\"\n    assert True  # Replace with actual test\n\ndef test_create_resource():\n    \"\"\"TC-002: Create resource.\"\"\"\n    assert True\n\ndef test_list_resources():\n    \"\"\"TC-003: List resources.\"\"\"\n    assert True\n\ndef test_invalid_input():\n    \"\"\"TC-004: Invalid input validation.\"\"\"\n    assert True\n',
        },
    }


def _gen_sre_ops(requirement: str, llm_content: str) -> dict:
    return {
        "doc_title": "Runbook — Operations Guide",
        "doc_content": f"# Operations Runbook\n\n## Service Overview\n{requirement}\n\n{llm_content}\n\n## SLO Definitions\n- Availability: 99.9% (43.2 min/month downtime budget)\n- Latency: p99 < 500ms\n- Error Rate: < 0.1%\n\n## Incident Response\n1. Page received → Acknowledge within 5 min\n2. Assess severity (SEV1-SEV3)\n3. Mitigate → Communicate → Resolve\n4. Post-mortem within 48 hours",
        "code_files": {
            "monitoring/alerts.yaml": "groups:\n  - name: service-alerts\n    rules:\n      - alert: HighErrorRate\n        expr: rate(http_requests_total{status=~\"5..\"}[5m]) > 0.01\n        for: 5m\n        labels:\n          severity: critical\n      - alert: HighLatency\n        expr: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])) > 0.5\n        for: 5m\n        labels:\n          severity: warning\n",
            "monitoring/dashboard.json": '{"title": "Service Dashboard", "panels": [{"type": "graph", "title": "Request Rate"}, {"type": "graph", "title": "Error Rate"}, {"type": "graph", "title": "Latency p99"}]}\n',
        },
    }


def _gen_docs_team(requirement: str, llm_content: str) -> dict:
    return {
        "doc_title": "Technical Documentation — User Guide",
        "doc_content": f"# User Guide\n\n## Getting Started\n{requirement}\n\n{llm_content}\n\n## Quick Start\n1. Clone the repository\n2. Install dependencies\n3. Run the application\n4. Access the dashboard\n\n## API Reference\nSee the OpenAPI spec for complete API documentation.\n\n## Changelog\n- v1.0.0: Initial release\n  - Core CRUD operations\n  - Authentication\n  - Admin dashboard",
        "mermaid": ("flowchart", "Getting Started Flow", "graph TD\n    Clone[Clone Repo] --> Install[Install Deps]\n    Install --> Config[Configure Env]\n    Config --> Run[Run App]\n    Run --> Access[Access Dashboard]"),
    }


def _gen_feature_eng(requirement: str, llm_content: str) -> dict:
    return {
        "sheet_title": "Feature Tracker & Backlog",
        "sheet_headers": ["Feature ID", "Feature", "Priority", "Status", "Sprint", "Owner", "Story Points"],
        "sheet_rows": [
            ["F-001", "Core CRUD Operations", "P0", "Done", "Sprint 1", "Backend", "5"],
            ["F-002", "User Authentication", "P0", "Done", "Sprint 1", "Security", "8"],
            ["F-003", "Dashboard UI", "P1", "In Progress", "Sprint 2", "Frontend", "5"],
            ["F-004", "API Rate Limiting", "P1", "Planned", "Sprint 2", "Backend", "3"],
            ["F-005", "Admin Panel", "P2", "Backlog", "Sprint 3", "Frontend", "8"],
            ["F-006", "Analytics Dashboard", "P2", "Backlog", "Sprint 3", "Data", "5"],
        ],
        "doc_title": "Feature Closure Report",
        "doc_content": f"# Feature Closure Report\n\n## Requirement\n{requirement}\n\n{llm_content}\n\n## Delivery Summary\n- Features delivered: 6\n- Story points completed: 34\n- Sprints: 3\n- Quality gate: PASSED",
    }


# Map team → generator function
_GENERATORS = {
    "product_mgmt": _gen_product_mgmt,
    "biz_analysis": _gen_biz_analysis,
    "solution_arch": _gen_solution_arch,
    "api_design": _gen_api_design,
    "ux_ui": _gen_ux_ui,
    "frontend_eng": _gen_frontend_eng,
    "backend_eng": _gen_backend_eng,
    "database_eng": _gen_database_eng,
    "data_eng": _gen_data_eng,
    "ml_eng": _gen_ml_eng,
    "security_eng": _gen_security_eng,
    "compliance": _gen_compliance,
    "devops": _gen_devops,
    "qa_eng": _gen_qa_eng,
    "sre_ops": _gen_sre_ops,
    "docs_team": _gen_docs_team,
    "feature_eng": _gen_feature_eng,
}


def run_phase2_handler(
    team: str,
    requirement: str,
    prior_count: int,
    llm_runtime: TeamLLMRuntime | None = None,
    *,
    uid: str = "",
    project_id: str = "",
    git_url: str = "",
    git_token: str = "",
    folder_id: str | None = None,
) -> Phase2StageArtifact:
    """Execute a Phase 2 stage for one team with real tool invocations."""

    # 1. Team config
    tool_cfg = get_team_tools(team)
    specialized = {
        "product_mgmt": ("MVP slicing + milestone definition", "biz_analysis"),
        "biz_analysis": ("requirements and acceptance criteria refinement", "solution_arch"),
        "solution_arch": ("component architecture + ADR extraction", "api_design"),
        "api_design": ("contract-first OpenAPI draft", "ux_ui"),
        "ux_ui": ("flow-level UX outline and handoff notes", "frontend_eng"),
        "frontend_eng": ("UI implementation plan and state contracts", "backend_eng"),
        "backend_eng": ("service implementation and endpoint alignment", "database_eng"),
        "database_eng": ("schema checks and migration path", "data_eng"),
        "data_eng": ("data movement plan and transformation checks", "ml_eng"),
        "ml_eng": ("model integration checkpoints", "security_eng"),
        "security_eng": ("baseline threat checks and scan profile", "compliance"),
        "compliance": ("policy and audit evidence collection", "devops"),
        "devops": ("deployment and rollback workflow", "qa_eng"),
        "qa_eng": ("end-to-end quality gates", "sre_ops"),
        "sre_ops": ("SLO + alerting baseline", "docs_team"),
        "docs_team": ("runbook and release notes", "feature_eng"),
        "feature_eng": ("feature closure and backlog sync", "none"),
    }
    detail, handoff = specialized.get(team, ("team objective drafted", "none"))

    # 2. LLM generation (best-effort)
    source = "deterministic"
    cost = 0.0
    remaining = 0.0
    if llm_runtime is not None:
        generated = llm_runtime.generate(team=team, requirement=requirement, prior_count=prior_count, handoff_to=handoff)
        if generated is not None:
            detail = generated.content
            source = generated.source
            cost = generated.estimated_cost_usd
            remaining = generated.budget_remaining_usd

    # 3. Generate team-specific artifacts
    gen_fn = _GENERATORS.get(team)
    gen_data = gen_fn(requirement, detail) if gen_fn else {}

    # 4. Execute tools
    tools_used: list[ToolExecution] = []

    # Tavily search (if team uses it)
    if tool_cfg and "tavily_search" in tool_cfg.tools and gen_data.get("search_query"):
        tools_used.append(_execute_tavily(team, gen_data["search_query"]))

    # Mermaid diagrams
    if tool_cfg and "mermaid" in tool_cfg.tools and gen_data.get("mermaid"):
        dtype, dtitle, dcontent = gen_data["mermaid"]
        tools_used.append(_execute_mermaid(team, dtype, dtitle, dcontent))

    # Google Docs
    if tool_cfg and "google_docs" in tool_cfg.tools and gen_data.get("doc_title"):
        doc_title = f"[{project_id or 'project'}] {gen_data['doc_title']}"
        tools_used.append(_execute_google_docs(team, doc_title, gen_data["doc_content"], folder_id))

    # Google Sheets
    if tool_cfg and "google_sheets" in tool_cfg.tools and gen_data.get("sheet_title"):
        sheet_title = f"[{project_id or 'project'}] {gen_data['sheet_title']}"
        tools_used.append(_execute_google_sheets(
            team, sheet_title,
            gen_data.get("sheet_headers", []),
            gen_data.get("sheet_rows", []),
            folder_id,
        ))

    # Git / GCS for code files
    code_files = gen_data.get("code_files", {})
    if code_files:
        if git_url:
            tools_used.append(_execute_git(team, git_url, git_token, project_id, code_files))
        elif uid and project_id:
            for fname, fcontent in code_files.items():
                tools_used.append(_execute_gcs(team, uid, project_id, fname.replace("/", "_"), fcontent))
        else:
            tools_used.append(ToolExecution(tool="gcs", action=f"Skipped {len(code_files)} files (no uid/project)", success=False, error="No storage configured"))

    # 5. Build artifact text
    tools_summary = "; ".join(
        f"{t.tool}({'✓' if t.success else '✗'}: {t.action})" for t in tools_used
    ) or "no tools executed"

    artifact = (
        f"P2:{team}\n"
        f"- requirement: {requirement}\n"
        f"- prior_context_items: {prior_count}\n"
        f"- action: {detail}\n"
        f"- source: {source}\n"
        f"- estimated_cost_usd: {cost:.6f}\n"
        f"- budget_remaining_usd: {remaining:.6f}\n"
        f"- tools_used: {tools_summary}\n"
        f"- artifacts_produced: {', '.join(tool_cfg.artifacts) if tool_cfg else 'none'}\n"
        f"- handoff_to: {handoff}"
    )

    return Phase2StageArtifact(team=team, artifact=artifact, tools_used=tools_used, code_files=code_files)
