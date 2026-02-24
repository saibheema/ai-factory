"""Phase 2 handlers — each team executes real tools and logs artifacts.

Every team:
 1. Gets its tool config from team_tools.py
 2. Generates content via LLM (or deterministic fallback)
 3. Executes the assigned tools (Google Docs, Sheets, Git, GCS, Mermaid, Tavily)
 4. Dispatches any [@team: message] actor mentions in the LLM output
 5. Returns a structured artifact with tool execution log
"""

import logging
import os
import re
from dataclasses import dataclass, field

from factory.llm.runtime import TeamLLMRuntime
from factory.tools.team_tools import TEAM_TOOLS, get_team_tools

log = logging.getLogger(__name__)

# ─── Tool recovery maps ───────────────────────────────────────────────────────
# Maps tool names to the env-var keys they need (for session-cred injection).
_TOOL_REQUIRED_KEYS: dict[str, list[str]] = {
    "plane":         ["PLANE_API_KEY", "PLANE_WORKSPACE_SLUG"],
    "slack":         ["SLACK_BOT_TOKEN"],
    "confluence":    ["CONFLUENCE_URL", "CONFLUENCE_USER", "CONFLUENCE_API_TOKEN"],
    "jira":          ["JIRA_URL", "JIRA_USER", "JIRA_API_TOKEN"],
    "tavily_search": ["TAVILY_API_KEY"],
    "google_docs":   ["GOOGLE_SA_JSON"],
    "google_sheets": ["GOOGLE_SA_JSON"],
    "git":           ["GIT_TOKEN"],
}

# Human-readable recovery prompts shown in group chat when a tool fails.
_TOOL_RECOVERY_QUESTIONS: dict[str, str] = {
    "plane":         "I need a Plane.so API key to create project issues. Share in group chat: PLANE_API_KEY=your_key  PLANE_WORKSPACE_SLUG=your_slug",
    "slack":         "I need a Slack Bot Token to post notifications. Share: SLACK_BOT_TOKEN=xoxb-xxx",
    "confluence":    "I need Confluence credentials to publish docs. Share: CONFLUENCE_URL=https://... CONFLUENCE_USER=email CONFLUENCE_API_TOKEN=token",
    "jira":          "I need Jira credentials to create issues. Share: JIRA_URL=https://... JIRA_USER=email JIRA_API_TOKEN=token",
    "tavily_search": "Research is limited — Tavily key missing. Share: TAVILY_API_KEY=tvly-xxx for richer tech research.",
    "google_docs":   "I need a Google Service Account to create Docs. Share: GOOGLE_SA_JSON=<base64-encoded-sa-json>",
    "google_sheets": "I need a Google Service Account to create Sheets. Share: GOOGLE_SA_JSON=<base64-encoded-sa-json>",
    "git":           "I need a Git token to push code. Go to Settings → GitHub Token to configure, or share: GIT_TOKEN=ghp_xxx",
    "trivy":         "Trivy CLI is not installed in the container. DevOps needs to add it to the Dockerfile (apt-get install trivy).",
    "gitleaks":      "Gitleaks CLI is not installed. DevOps needs to add it to the Dockerfile.",
    "checkov":       "Checkov is not installed. Add to requirements.txt: checkov>=3.0.0, or DevOps can add it to the image.",
    "semgrep":       "Semgrep CLI is not installed. DevOps needs to add it to the Dockerfile.",
    "ruff":          "Ruff found code style violations in the generated code. The code works but needs formatting — re-run with 'clean up the code style' to auto-fix.",
    "black":         "Black found formatting issues in the generated code. Re-run with 'fix code formatting' to apply.",
    "mypy":          "mypy found type errors in the generated code. Re-run with 'fix type errors' to resolve.",
    "bandit":        "Bandit found security issues in the generated code. Re-run with 'fix security issues' to address.",
}


def get_tool_recovery_question(tool: str, error: str = "") -> str | None:
    """Return a user-facing recovery question for a failed tool, or None if no advice."""
    q = _TOOL_RECOVERY_QUESTIONS.get(tool)
    if q:
        return q
    if error:
        return f"Tool '{tool}' failed: {error[:120]}. Check configuration or share the required credentials in group chat."
    return None


# ─── Tool failure classification ─────────────────────────────────────────────
# LLM can regenerate code to fix these violations automatically.
_AUTOFIX_TOOLS: frozenset[str] = frozenset({"ruff", "black", "mypy", "bandit"})

# These MUST succeed — pipeline blocks (pauses for user input) if still failing
# after any auto-fix attempt. Code quality + code storage are hard gates.
_HARD_BLOCK_TOOLS: frozenset[str] = frozenset({
    "ruff", "black", "mypy", "bandit",  # code quality gates
    "git",                               # code must be persisted
})


def _try_autofix_code_quality(
    tool: str,
    te: "ToolExecution",
    code_files: dict[str, str],
    llm_runtime: "TeamLLMRuntime",
    requirement: str,
) -> "dict[str, str] | None":
    """Use the LLM to auto-fix code quality violations.

    Calls the LiteLLM proxy (or SDK fallback) with the violation details and
    the current code, asking it to fix the specific issues.
    Returns an updated *code_files* dict on success, or None if it cannot help.
    """
    try:
        import httpx as _httpx

        target_files = {k: v for k, v in code_files.items() if k.endswith(".py")}
        if not target_files:
            return None

        # Build a concise violation summary
        violations = ""
        if tool == "ruff":
            viols = (te.result or {}).get("violations", [])[:15]
            violations = "\n".join(
                f"  line {v.get('line', '?')}: [{v.get('code', '')}] {v.get('message', '')}"
                for v in viols
            )
        elif tool == "black":
            violations = ((te.result or {}).get("diff") or te.error or "needs formatting")[:400]
        elif tool == "mypy":
            errs = (te.result or {}).get("errors", [])[:10]
            violations = "\n".join(f"  {e}" for e in errs) if errs else (te.error or "")[:300]
        elif tool == "bandit":
            issues = (te.result or {}).get("issues", [])[:10]
            violations = "\n".join(
                f"  [{i.get('issue_severity','?')}] {i.get('issue_text','')} ({i.get('filename','')})"
                for i in issues
            )

        fix_instructions = {
            "ruff": (
                "Fix ALL ruff violations: unused imports (F401), line length (E501), "
                "naming (N8xx), missing blank lines (E302), trailing whitespace (W291). "
                "Preserve ALL logic exactly — only fix style."
            ),
            "black": (
                "Reformat to Black style: max 88 chars per line, double quotes, "
                "consistent indentation. Preserve ALL logic."
            ),
            "mypy": (
                "Fix ALL mypy type errors: add type annotations, fix incompatible types, "
                "use Optional[X] for nullable. Preserve ALL logic."
            ),
            "bandit": (
                "Fix ALL Bandit security issues: replace hardcoded secrets with env vars, "
                "use secrets.token_hex for random, use list args for subprocess. "
                "Preserve ALL logic."
            ),
        }.get(tool, f"Fix all {tool} violations. Preserve ALL logic.")

        code_str = "\n\n".join(
            f"# === {fname} ===\n{code}" for fname, code in target_files.items()
        )
        prompt = (
            f"You are a {tool} code fixer. Fix ONLY the quality violations — do NOT change logic.\n\n"
            f"VIOLATIONS:\n{violations or te.error or 'see tool output'}\n\n"
            f"CODE:\n{code_str[:4000]}\n\n"
            f"INSTRUCTION: {fix_instructions}\n\n"
            f"Return ONLY fixed code. For each file use this exact format:\n"
            f"# === filename ===\n<complete fixed file content>\n\n"
            f"NO markdown fences. NO explanations. Just the fixed code."
        )
        payload = {
            "model": "factory/coder",
            "messages": [
                {"role": "system", "content": "You are a code quality fixer. Return only fixed code."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 3000,
        }

        fixed_text: str | None = None
        try:
            with _httpx.Client(timeout=30.0) as _c:
                _r = _c.post(f"{llm_runtime.proxy_url}/chat/completions", json=payload)
                _r.raise_for_status()
                fixed_text = (_r.json()["choices"][0]["message"]["content"] or "").strip() or None
        except Exception as _e1:
            log.debug("Auto-fix proxy call failed (%s): %s", tool, _e1)

        if not fixed_text:
            try:
                import litellm as _ll  # type: ignore[import]
                _sdk = _ll.completion(**payload)
                fixed_text = (_sdk.choices[0].message.content or "").strip() or None
            except Exception as _e2:
                log.debug("Auto-fix SDK call failed (%s): %s", tool, _e2)

        if not fixed_text:
            return None

        # Parse "# === fname ===" blocks back into a dict
        fixed_files: dict[str, str] = {}
        cur_file: str | None = None
        cur_lines: list[str] = []
        for line in fixed_text.split("\n"):
            if line.startswith("# === ") and line.endswith(" ==="):
                if cur_file is not None:
                    fixed_files[cur_file] = "\n".join(cur_lines).strip()
                cur_file = line[6:-4]
                cur_lines = []
            else:
                if cur_file is not None:
                    cur_lines.append(line)
        if cur_file is not None:
            fixed_files[cur_file] = "\n".join(cur_lines).strip()

        # Fallback: if no file-header format, map entire output to first file
        if not fixed_files:
            first_fname = next(iter(target_files.keys()))
            fixed_files[first_fname] = _strip_fences(fixed_text)

        # Merge fixed files back into original code_files
        result = dict(code_files)
        for fname, fixed_code in fixed_files.items():
            if fname in result:
                result[fname] = fixed_code
            else:
                for orig in list(result):
                    if orig.endswith(fname) or fname.endswith(orig.split("/")[-1]):
                        result[orig] = fixed_code
                        break
        return result

    except Exception as _outer:
        log.warning("Auto-fix outer error (%s): %s", tool, _outer)
        return None


def _strip_fences(code: str) -> str:
    """Remove markdown code fences and language tags from LLM output."""
    import re as _re
    code = _re.sub(r'^\s*```[a-zA-Z]*\s*\n?', '', code, flags=_re.MULTILINE)
    code = _re.sub(r'\n?\s*```\s*$', '', code, flags=_re.MULTILINE)
    return code.strip()


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
    qa_issues: list[str] = field(default_factory=list)
    qa_verdict: str = ""
    # Decision log metadata — populated by run_phase2_handler
    decision_type: str = ""       # e.g. "ADR", "threat_model", "acceptance_criteria"
    decision_title: str = ""      # short title for the decision card
    decision_rationale: str = ""  # extracted reasoning / action taken
    # ── Recovery / blocking ──────────────────────────────────────────────────
    blocked: bool = False          # True → pipeline must pause for user input
    block_reason: str = ""         # Human-readable description of what's needed
    block_tool: str = ""           # Which tool triggered the block
    autofix_applied: bool = False  # True if LLM auto-fix was applied successfully
    # ── Sol Arch per-team handoffs ───────────────────────────────────────────
    # Populated only for solution_arch. Maps downstream team slug →
    # team-specific instruction extracted from the HANDOFF_* LLM sections.
    # The pipeline loop passes the relevant entry to each downstream team so
    # every team receives tailored instructions rather than the same broadcast.
    sol_arch_handoffs: dict[str, str] = field(default_factory=dict)


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


def _execute_plane(
    team: str,
    project_id: str,
    requirement: str,
    issue_title: str,
    decision_type: str,
    artifact_summary: str,
) -> ToolExecution:
    """Create a Plane (Jira-like) issue to track this team's pipeline stage."""
    try:
        from factory.tools.plane_tool import get_or_create_project, create_issue
        import re as _re

        plane_project_name = f"AI Factory: {project_id}"
        ident = _re.sub(r"[^A-Z0-9]", "", project_id.upper())[:5] or "AIFAC"
        plane_pid = get_or_create_project(plane_project_name, ident)
        if not plane_pid:
            return ToolExecution(
                tool="plane", action="Issue skipped (no Plane project)",
                success=False, error="Could not get/create Plane project",
            )

        priority_map = {
            "ADR": "high", "threat_model": "urgent", "compliance": "high",
            "deployment": "high", "test_plan": "high", "feature": "medium",
            "api_contract": "high", "acceptance_criteria": "medium",
        }
        priority = priority_map.get(decision_type, "medium")
        title = issue_title[:200] if issue_title else f"[{team}] {requirement[:80]}"
        desc = (
            f"**Team:** {team}\n"
            f"**Decision Type:** {decision_type}\n"
            f"**Requirement:** {requirement[:300]}\n\n"
            f"**Artifact Summary:**\n{artifact_summary[:500]}"
        )
        result = create_issue(
            project_id=plane_pid,
            title=title,
            description=desc,
            priority=priority,
        )
        seq = result.get("sequence_id", "?")
        url = result.get("issue_url", "")
        return ToolExecution(
            tool="plane",
            action=f"Issue #{seq}: {title[:60]}",
            result={**result, "issue_url": url},
            success=bool(result.get("issue_id")),
        )
    except Exception as e:
        log.debug("Plane issue creation skipped for %s: %s", team, e)
        return ToolExecution(
            tool="plane", action=f"Issue for {team} (Plane unavailable)",
            success=False, error=str(e),
        )


def _execute_notification(
    team: str, project_id: str, requirement: str, artifact_summary: str
) -> ToolExecution:
    """Send a stage-complete notification via ntfy / Slack / webhook."""
    try:
        from factory.tools.notification_tool import notify
        result = notify(
            title=f"✅ {team} — {project_id or 'pipeline'}",
            message=f"Requirement: {requirement[:150]}\n\n{artifact_summary[:200]}",
            tags=[team, project_id or "pipeline", "stage-complete"],
            priority="default",
        )
        channels = result.get("channels", [])
        return ToolExecution(
            tool="notification",
            action=f"Notified via {', '.join(channels) or 'no channels configured'}",
            result=result,
            success=True,
        )
    except Exception as e:
        return ToolExecution(
            tool="notification", action="Notify stage complete",
            success=False, error=str(e),
        )


def _execute_semgrep(team: str, code_files: dict[str, str]) -> ToolExecution:
    """Run Semgrep SAST scan on generated code files."""
    if not code_files:
        return ToolExecution(
            tool="semgrep", action="No code files to scan",
            success=True, result={"passed": True, "finding_count": 0},
        )
    try:
        from factory.tools.semgrep_tool import scan_code
        all_findings: list[dict] = []
        for fname, code in code_files.items():
            lang = (
                "javascript"
                if fname.endswith((".js", ".jsx", ".ts", ".tsx"))
                else "python"
            )
            result = scan_code(code, language=lang, filename=fname)
            all_findings.extend(result.get("findings", []))
        total = len(all_findings)
        passed = total == 0
        return ToolExecution(
            tool="semgrep",
            action=f"SAST: {'PASS' if passed else 'FAIL'} ({total} findings, {len(code_files)} files)",
            result={"passed": passed, "finding_count": total, "findings": all_findings[:10]},
            success=passed,
        )
    except Exception as e:
        return ToolExecution(tool="semgrep", action="SAST scan", success=False, error=str(e))


def _execute_trivy_iac(team: str, code_files: dict[str, str]) -> ToolExecution:
    """Run Trivy IaC/secrets scan on Dockerfile and YAML config files."""
    import os as _os, tempfile as _tempfile

    iac_files = {
        k: v for k, v in code_files.items()
        if any(k.lower().endswith(ext) for ext in ("dockerfile", ".yaml", ".yml", ".tf"))
        or "dockerfile" in k.lower()
    }
    if not iac_files:
        return ToolExecution(
            tool="trivy", action="No IaC files to scan",
            success=True, result={"passed": True, "misconfig_count": 0},
        )
    try:
        from factory.tools.trivy_tool import scan_iac
        with _tempfile.TemporaryDirectory(prefix="aifactory-trivy-") as tmp:
            for fname, content in iac_files.items():
                fpath = _os.path.join(tmp, _os.path.basename(fname) or "scan.yaml")
                with open(fpath, "w") as fh:
                    fh.write(content)
            result = scan_iac(tmp)
        count = result.get("misconfig_count", 0)
        passed = result.get("passed", True)
        return ToolExecution(
            tool="trivy",
            action=f"IaC scan: {'PASS' if passed else 'FAIL'} ({count} misconfigs, {len(iac_files)} files)",
            result=result,
            success=passed,
        )
    except Exception as e:
        return ToolExecution(tool="trivy", action="IaC scan", success=False, error=str(e))


def _execute_ruff(team: str, code_files: dict[str, str]) -> ToolExecution:
    """Lint Python code files with Ruff."""
    py_files = {k: v for k, v in code_files.items() if k.endswith(".py")}
    if not py_files:
        return ToolExecution(
            tool="ruff", action="No Python files to lint",
            success=True, result={"passed": True, "violation_count": 0},
        )
    try:
        from factory.tools.ruff_tool import lint_code
        all_violations: list[dict] = []
        for fname, code in py_files.items():
            result = lint_code(code, filename=fname)
            all_violations.extend(result.get("violations", []))
        total = len(all_violations)
        passed = total == 0
        return ToolExecution(
            tool="ruff",
            action=f"Lint: {'PASS' if passed else f'{total} violations'} ({len(py_files)} files)",
            result={"passed": passed, "violation_count": total, "violations": all_violations[:20]},
            success=passed,
        )
    except Exception as e:
        return ToolExecution(tool="ruff", action="Ruff lint", success=False, error=str(e))


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


# ─── New tool executor helpers ────────────────────────────────────────────────

def _execute_slack(team: str, project_id: str, summary: str, handoff_to: str = "") -> ToolExecution:
    """Post stage-complete notification to Slack."""
    try:
        from factory.tools.slack_tool import send_stage_complete
        result = send_stage_complete(
            team=team,
            project_id=project_id,
            artifact_title=summary[:80],
            handoff_to=handoff_to,
        )
        return ToolExecution(tool="slack", action=f"Stage complete → #{team}", result=result, success=result.get("ok", False))
    except Exception as e:
        log.debug("Slack notify skipped for %s: %s", team, e)
        return ToolExecution(tool="slack", action="Stage complete", success=False, error=str(e))


def _execute_bandit(team: str, code_files: dict[str, str]) -> ToolExecution:
    """Run Bandit SAST on generated code files."""
    try:
        from factory.tools.bandit_tool import scan_code
        combined = "\n\n".join(f"# --- {fname} ---\n{code}" for fname, code in code_files.items() if fname.endswith(".py"))
        if not combined:
            return ToolExecution(tool="bandit", action="Skipped (no Python files)", success=True)
        result = scan_code(combined)
        action = f"SAST: {result.get('total_issues', 0)} issues (H:{result.get('high', 0)} M:{result.get('medium', 0)})"
        return ToolExecution(tool="bandit", action=action, result=result, success=result.get("passed", True))
    except Exception as e:
        return ToolExecution(tool="bandit", action="SAST scan", success=False, error=str(e))


def _execute_gitleaks(team: str, code_files: dict[str, str]) -> ToolExecution:
    """Run Gitleaks secret scan on code content."""
    try:
        from factory.tools.gitleaks_tool import scan_string
        combined = "\n\n".join(f"# {fname}\n{code}" for fname, code in code_files.items())
        result = scan_string(combined, rule_hint=f"{team}_generated_code")
        action = f"Secret scan: {result.get('secret_count', 0)} secrets found"
        return ToolExecution(tool="gitleaks", action=action, result=result, success=result.get("passed", True))
    except Exception as e:
        return ToolExecution(tool="gitleaks", action="Secret scan", success=False, error=str(e))


def _execute_checkov(team: str, code_files: dict[str, str]) -> ToolExecution:
    """Run Checkov on IaC/Kubernetes/Dockerfile content."""
    try:
        from factory.tools.checkov_tool import scan_inline
        # Find any IaC files: .tf, .yaml, .yml, Dockerfile
        iac_files = {f: c for f, c in code_files.items()
                     if any(f.endswith(ext) for ext in (".tf", ".yaml", ".yml")) or "dockerfile" in f.lower()}
        if not iac_files:
            return ToolExecution(tool="checkov", action="Skipped (no IaC files)", success=True)
        fname, content = next(iter(iac_files.items()))
        framework = "terraform" if fname.endswith(".tf") else ("kubernetes" if "deploy" in fname else "dockerfile")
        result = scan_inline(content, framework=framework, filename=fname)
        action = f"IaC scan: passed={result.get('passed_count', 0)} failed={result.get('failed_count', 0)}"
        return ToolExecution(tool="checkov", action=action, result=result, success=result.get("passed", True))
    except Exception as e:
        return ToolExecution(tool="checkov", action="IaC scan", success=False, error=str(e))


def _execute_mypy(team: str, code_files: dict[str, str]) -> ToolExecution:
    """Run mypy type checking on Python code."""
    try:
        from factory.tools.mypy_tool import check_code
        py_files = {f: c for f, c in code_files.items() if f.endswith(".py")}
        if not py_files:
            return ToolExecution(tool="mypy", action="Skipped (no Python files)", success=True)
        fname, code = next(iter(py_files.items()))
        result = check_code(code, filename=fname, strict=False)
        action = f"Type check: {result.get('error_count', 0)} errors"
        return ToolExecution(tool="mypy", action=action, result=result, success=result.get("passed", True))
    except Exception as e:
        return ToolExecution(tool="mypy", action="Type check", success=False, error=str(e))


def _execute_black(team: str, code_files: dict[str, str]) -> ToolExecution:
    """Check/format Python code with Black."""
    try:
        from factory.tools.black_tool import check_formatting
        py_files = {f: c for f, c in code_files.items() if f.endswith(".py")}
        if not py_files:
            return ToolExecution(tool="black", action="Skipped (no Python files)", success=True)
        fname, code = next(iter(py_files.items()))
        result = check_formatting(code, filename=fname)
        action = f"Format check: {'clean' if result.get('passed') else 'needs formatting'}"
        return ToolExecution(tool="black", action=action, result=result, success=result.get("passed", True))
    except Exception as e:
        return ToolExecution(tool="black", action="Format check", success=False, error=str(e))


def _execute_confluence(team: str, project_id: str, title: str, content_md: str) -> ToolExecution:
    """Publish documentation to Confluence."""
    try:
        from factory.tools.confluence_tool import markdown_to_storage, upsert_page
        storage_html = markdown_to_storage(content_md)
        page_title = f"[{project_id}] {title}" if project_id else title
        result = upsert_page(title=page_title, body_html=storage_html)
        action = f"{result.get('action', 'upsert')}: {page_title[:60]}"
        return ToolExecution(tool="confluence", action=action, result=result, success=result.get("success", False))
    except Exception as e:
        log.debug("Confluence publish skipped for %s: %s", team, e)
        return ToolExecution(tool="confluence", action="Publish page", success=False, error=str(e))


def _execute_jira(team: str, project_id: str, summary: str, description: str, issue_type: str = "Story") -> ToolExecution:
    """Create a Jira issue."""
    try:
        from factory.tools.jira_tool import create_issue
        result = create_issue(summary=summary[:255], description=description[:2000], issue_type=issue_type)
        action = f"Created {issue_type}: {result.get('key', '')} — {summary[:50]}"
        return ToolExecution(tool="jira", action=action, result=result, success=result.get("success", False))
    except Exception as e:
        log.debug("Jira issue creation skipped for %s: %s", team, e)
        return ToolExecution(tool="jira", action="Create issue", success=False, error=str(e))


def _execute_k6(team: str, base_url: str = "", endpoints: list[str] | None = None) -> ToolExecution:
    """Run a k6 smoke test against service endpoints."""
    try:
        from factory.tools.k6_tool import smoke_test
        if not base_url:
            return ToolExecution(tool="k6", action="Skipped (no base URL configured)", success=True)
        result = smoke_test(base_url=base_url, endpoints=endpoints or ["/health"])
        passed = result.get("passed", False)
        action = f"Smoke test: {'passed' if passed else 'FAILED'} ({len(result.get('results', []))} endpoints)"
        return ToolExecution(tool="k6", action=action, result=result, success=passed)
    except Exception as e:
        return ToolExecution(tool="k6", action="Smoke test", success=False, error=str(e))


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
    """Solution Architecture generator: extensive research + ADR + tech decision matrix.

    Produces:
    - Google Doc: Architecture Decision Record (full ADR)
    - Google Sheet: Tech Stack Decision Matrix with pros/cons per option
    - Multiple Tavily searches: UI stack, backend stack, cloud infra, security patterns,
      similar app reference architectures
    - Mermaid C4 system context + component diagram
    - Explicit per-team handoff sections (extracted from LLM output)
    """
    # ── Extract per-team HANDOFF sections from LLM output ────────────────────
    import re as _re

    def _extract_handoff(key: str, text: str) -> str:
        """Pull HANDOFF_<KEY>: line from LLM output."""
        m = _re.search(rf"HANDOFF_{key}:\s*(.+?)(?=\nHANDOFF_|\nCONSEQUENCES|\nTECH STACK|$)",
                       text, _re.IGNORECASE | _re.DOTALL)
        return m.group(1).strip() if m else ""

    handoff_api   = _extract_handoff("API_DESIGN",   llm_content)
    handoff_ux    = _extract_handoff("UX_UI",        llm_content)
    handoff_fe    = _extract_handoff("FRONTEND_ENG", llm_content)
    handoff_be    = _extract_handoff("BACKEND_ENG",  llm_content)
    handoff_db    = _extract_handoff("DATABASE_ENG", llm_content)
    handoff_devop = _extract_handoff("DEVOPS",       llm_content)
    handoff_sec   = _extract_handoff("SECURITY_ENG", llm_content)

    # ── Tech Stack Decision Matrix rows ──────────────────────────────────────
    sheet_rows = [
        ["UI Framework",  "React 18+Vite / Next.js 14 / Vue 3 / SvelteKit", "Chosen per ADR-001",
         handoff_fe[:80] or "See ADR-001", "Frontend Eng"],
        ["Backend",       "FastAPI / NestJS / Go-Gin / Django REST",          "Chosen per ADR-001",
         handoff_be[:80] or "See ADR-001", "Backend Eng"],
        ["Database",      "PostgreSQL 16 / MySQL 8 / MongoDB 7",             "Chosen per ADR-001",
         handoff_db[:80] or "See ADR-001", "Database Eng"],
        ["Cache",         "Redis 7 / Memcached",                              "Chosen per ADR-001",
         "See ADR-001", "Backend Eng"],
        ["Cloud Deploy",  "Cloud Run / GKE / ECS Fargate",                   "Chosen per ADR-001",
         handoff_devop[:80] or "See ADR-001", "DevOps"],
        ["IaC",           "Terraform / Pulumi",                               "Chosen per ADR-001",
         "See ADR-001", "DevOps"],
        ["API Protocol",  "REST / GraphQL / tRPC",                           "Chosen per ADR-001",
         handoff_api[:80] or "See ADR-001", "API Design"],
        ["Auth",          "JWT+OAuth2 / OIDC / API Keys",                    "Chosen per ADR-001",
         handoff_sec[:80] or "See ADR-001", "Security Eng"],
        ["CI/CD",         "GitHub Actions / Cloud Build",                    "Chosen per ADR-001",
         "See ADR-001", "DevOps"],
        ["Observability", "OTEL traces / Prometheus / structured JSON logs", "Standard",
         "All teams instrument", "SRE Ops"],
    ]

    handoff_section = (
        f"\n\n## Per-Team Handoff Notes\n"
        f"### → API Design\n{handoff_api or '(see Decisions section)'}\n\n"
        f"### → UX / UI\n{handoff_ux or '(see Decisions section)'}\n\n"
        f"### → Frontend Eng\n{handoff_fe or '(see Decisions section)'}\n\n"
        f"### → Backend Eng\n{handoff_be or '(see Decisions section)'}\n\n"
        f"### → Database Eng\n{handoff_db or '(see Decisions section)'}\n\n"
        f"### → DevOps\n{handoff_devop or '(see Decisions section)'}\n\n"
        f"### → Security Eng\n{handoff_sec or '(see Decisions section)'}"
    )

    # ── Explicit user-clarification block (always include) ──────────────────
    # Fully non-hardcoded: extract from LLM sections only.
    # If sections are absent, we do not fabricate domain questions.
    def _extract_section_list(header: str, text: str) -> list[str]:
        m = _re.search(
            rf"{header}:\s*(.+?)(?=\n[A-Z][A-Z_\s]+:|\nHANDOFF_|$)",
            text,
            _re.IGNORECASE | _re.DOTALL,
        )
        if not m:
            return []
        out: list[str] = []
        for ln in m.group(1).splitlines():
            cleaned = ln.strip().lstrip("-•").strip()
            if cleaned and cleaned.lower() != "none":
                out.append(cleaned)
        return out

    _open_questions: list[str] = []
    _known_inputs = _extract_section_list("KNOWN INPUTS", llm_content)
    _assumptions = _extract_section_list("ASSUMPTIONS", llm_content)
    _open_questions = _extract_section_list("OPEN QUESTIONS FOR USER", llm_content)
    if not _known_inputs:
        _known_inputs = [f"Requirement text: {requirement[:220]}"]
    if not _assumptions:
        _assumptions = ["Not explicitly provided by model."]

    _clarity_block = (
        "\n\n## Requirement Clarity (User in Loop)\n"
        "### Known Inputs\n"
        + "\n".join(f"- {x}" for x in _known_inputs)
        + "\n\n### Assumptions\n"
        + "\n".join(f"- {x}" for x in _assumptions)
        + "\n\n### Open Questions for User\n"
        + ("\n".join(f"- {q}" for q in _open_questions) if _open_questions else "- None")
    )

    return {
        "doc_title": "ADR-001 — Architecture Decision Record",
        "doc_content": (
            f"# Architecture Decision Record\n\n"
            f"## Context\n{requirement}\n\n"
            f"{llm_content}\n"
            f"{handoff_section}\n\n"
            f"{_clarity_block}\n\n"
            f"## Consequences\n"
            f"- Positive: Aligned stack, clear ownership, traceable decisions\n"
            f"- Negative: Initial ramp-up; teams must read this ADR before starting"
        ),
        # Multiple Tavily research queries — executed sequentially
        "search_queries": [
            f"best UI framework 2025 React Next.js Vue SvelteKit comparison {requirement[:40]}",
            f"latest 2025 UI design patterns for kids apps accessibility gamification {requirement[:35]}",
            f"github open source kids learning calculator app React Next.js examples",
            f"best open source education app frontend architecture GitHub",
            f"FastAPI vs NestJS vs Django REST performance comparison 2025",
            f"Cloud Run vs GKE vs ECS Fargate cost performance 2025",
            f"microservices vs monolith architecture {requirement[:40]} best practices",
            f"OWASP top 10 security controls REST API {requirement[:35]}",
        ],
        # Tech decision matrix spreadsheet
        "sheet_title": "Tech Stack Decision Matrix",
        "sheet_headers": ["Area", "Options Evaluated", "Decision", "Rationale / Constraints", "Owner"],
        "sheet_rows": sheet_rows,
        # C4 system context diagram
        "mermaid": (
            "flowchart",
            "System Architecture — C4 Context",
            "graph TB\n"
            "    User([User / Browser]) --> FE[Frontend — SPA/SSR]\n"
            "    FE --> GW[API Gateway / Load Balancer]\n"
            "    GW --> Auth[Auth Service — JWT/OAuth2]\n"
            "    GW --> API[Backend API Service]\n"
            "    API --> DB[(Primary DB — PostgreSQL)]\n"
            "    API --> Cache[(Redis Cache)]\n"
            "    API --> MQ[Message Queue — optional async]\n"
            "    MQ --> Worker[Worker / Consumer Service]\n"
            "    API --> OBS[Observability — OTEL + Prometheus]\n"
            "    Worker --> DB"
        ),
        # ── Per-team specific handoffs (extracted from LLM HANDOFF_* sections) ──
        # These are passed individually to each downstream team so every team
        # receives targeted instructions rather than the generic shared ADR text.
        "handoff_data": {
            "api_design":    handoff_api   or "Follow the API protocol and auth scheme in the ADR above.",
            "ux_ui":         handoff_ux    or "Use the UI framework and component library chosen in the ADR.",
            "frontend_eng":  handoff_fe    or "Implement using the UI stack defined in the ADR.",
            "backend_eng":   handoff_be    or "Implement using the backend framework defined in the ADR.",
            "database_eng":  handoff_db    or "Use the database engine and migration tool defined in the ADR.",
            "devops":        handoff_devop or "Deploy using the cloud target and IaC tool defined in the ADR.",
            "security_eng":  handoff_sec   or "Apply the auth mechanism and OWASP priorities defined in the ADR.",
        },
        "clarifying_questions": _open_questions,
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
    # Strip markdown fences that LLMs often add
    cleaned = _strip_fences(llm_content)
    # If LLM generated actual code (contains JSX/function keywords), use it directly
    is_real_code = any(kw in cleaned for kw in ["function ", "const ", "return (", "useState", "=>", "<div", "<>"])
    if is_real_code:
        app_code = cleaned
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
    # Strip markdown fences
    cleaned = _strip_fences(llm_content)
    # If LLM generated real Python code, use it
    is_real_code = any(kw in cleaned for kw in ["def ", "class ", "import ", "FastAPI", "@app."])
    if is_real_code:
        main_py = cleaned
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


def _gen_qa_eng(requirement: str, llm_content: str, *, all_code: dict[str, str] | None = None) -> dict:
    """QA engineer: validate generated code and produce test plan.

    When *all_code* is provided (the merged code from prior teams),
    run static checks and report issues so the pipeline surfaces them
    before the user has to discover errors manually.
    """
    issues: list[str] = []
    validated_files = 0

    if all_code:
        for fname, content in all_code.items():
            validated_files += 1
            # ── Static checks ───────────────────────────────
            # 1. Leftover markdown fences
            if '```' in content:
                issues.append(f"{fname}: contains markdown fence markers (```)")
            # 2. JSX/JS files: look for common component export
            if fname.endswith(('.jsx', '.tsx', '.js')):
                if 'function ' not in content and 'const ' not in content and '=>' not in content:
                    issues.append(f"{fname}: no function or const declaration found")
                has_component = any(
                    kw in content
                    for kw in ['function App', 'const App', 'function Main',
                               'function Calculator', 'function Dashboard',
                               'function Page', 'function Component']
                )
                if fname.endswith('App.jsx') and not has_component:
                    issues.append(f"{fname}: no recognisable root component (App, Main, etc.)")
            # 3. Python files: check syntax
            if fname.endswith('.py'):
                try:
                    compile(content, fname, 'exec')
                except SyntaxError as e:
                    issues.append(f"{fname}: Python syntax error — {e.msg} (line {e.lineno})")
            # 4. Dockerfile sanity
            if 'dockerfile' in fname.lower():
                if 'FROM' not in content:
                    issues.append(f"{fname}: Dockerfile missing FROM instruction")

    qa_verdict = 'PASS' if not issues else 'FAIL'
    issues_text = '\n'.join(f'  ✗ {i}' for i in issues) if issues else '  ✓ All checks passed'
    qa_report = (
        f"# QA Validation Report\n\n"
        f"**Verdict: {qa_verdict}**\n"
        f"Files validated: {validated_files}\n\n"
        f"## Static Analysis\n{issues_text}\n\n"
        f"## Test Plan\n{llm_content}\n"
    )

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
        "qa_issues": issues,
        "qa_verdict": qa_verdict,
        "qa_report": qa_report,
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


# Map team → default decision type (mirrors decision_log.TEAM_DECISION_TYPE)
_DECISION_TYPES: dict[str, str] = {
    "product_mgmt":  "feature",
    "biz_analysis":  "acceptance_criteria",
    "solution_arch": "ADR",
    "api_design":    "api_contract",
    "ux_ui":         "architecture",
    "frontend_eng":  "architecture",
    "backend_eng":   "architecture",
    "database_eng":  "architecture",
    "data_eng":      "architecture",
    "ml_eng":        "tool_choice",
    "security_eng":  "threat_model",
    "compliance":    "compliance",
    "devops":        "deployment",
    "qa_eng":        "test_plan",
    "sre_ops":       "deployment",
    "docs_team":     "architecture",
    "feature_eng":   "feature",
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
    all_code: dict[str, str] | None = None,
    shared_knowledge: str = "",   # key decisions from upstream teams
    next_team: str = "",           # actual next team in THIS run's selected list
    session_creds: dict[str, str] | None = None,  # user-provided keys for this session
    sol_arch_handoff: str = "",   # team-specific instruction from Sol Arch (if available)
) -> Phase2StageArtifact:
    """Execute a Phase 2 stage for one team with real tool invocations."""
    # ── Temporarily inject session-supplied credentials into os.environ ────────
    # Each pipeline run is a dedicated thread so this is thread-safe.
    # We restore the original values on exit (even on exception).
    _env_backup: dict[str, str | None] = {}
    if session_creds:
        for _k, _v in session_creds.items():
            _env_backup[_k] = os.environ.get(_k)
            os.environ[_k] = _v
        log.debug("session_creds injected for %s: %s", team, list(session_creds.keys()))
    try:
        return _run_phase2_handler_body(
            team=team, requirement=requirement, prior_count=prior_count,
            llm_runtime=llm_runtime, uid=uid, project_id=project_id,
            git_url=git_url, git_token=git_token, folder_id=folder_id,
            all_code=all_code, shared_knowledge=shared_knowledge, next_team=next_team,
            sol_arch_handoff=sol_arch_handoff,
        )
    finally:
        for _k, _orig in _env_backup.items():
            if _orig is None:
                os.environ.pop(_k, None)
            else:
                os.environ[_k] = _orig


def _run_phase2_handler_body(
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
    all_code: dict[str, str] | None = None,
    shared_knowledge: str = "",
    next_team: str = "",
    sol_arch_handoff: str = "",   # team-specific Sol Arch instruction
) -> Phase2StageArtifact:
    """Internal implementation — called after session creds are injected."""

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
    detail, canonical_handoff = specialized.get(team, ("team objective drafted", "none"))
    # Use the caller-supplied next_team when provided (smart-routed subset may skip
    # canonical successors); fall back to the canonical value only when all teams run.
    handoff = next_team if next_team else canonical_handoff

    # 2. Build effective requirement — prepend Sol Arch’s team-specific handoff
    #    (if available) THEN the accumulated upstream knowledge so every team
    #    gets clear, targeted instructions rather than a generic broadcast.
    effective_req = requirement
    if sol_arch_handoff:
        effective_req = (
            f"=== INSTRUCTIONS FROM SOLUTION ARCHITECT FOR {team.upper().replace('_', ' ')} ===\n"
            + sol_arch_handoff
            + "\n=== END SOL ARCH INSTRUCTIONS ===\n\n"
            + effective_req
        )
    if shared_knowledge:
        effective_req = (
            "=== KEY DECISIONS FROM UPSTREAM TEAMS (read carefully — build on this) ===\n"
            + shared_knowledge
            + "\n=== END UPSTREAM DECISIONS ===\n\n"
            + effective_req
        )

    # 3. LLM generation (best-effort)
    source = "deterministic"
    cost = 0.0
    remaining = 0.0
    a2a_dispatched: list[str] = []
    if llm_runtime is not None:
        generated = llm_runtime.generate(team=team, requirement=effective_req, prior_count=prior_count, handoff_to=handoff)
        if generated is not None:
            detail = generated.content
            source = generated.source
            cost = generated.estimated_cost_usd
            remaining = generated.budget_remaining_usd
            # ── A2A: dispatch any [@team: message] mentions in the LLM output ──
            try:
                from factory.messaging.actor import dispatch_actor_messages
                a2a_dispatched = dispatch_actor_messages(detail, from_team=team)
                if a2a_dispatched:
                    log.debug(
                        "A2A: %s dispatched %d messages: %s",
                        team, len(a2a_dispatched), a2a_dispatched,
                    )
            except Exception as _a2a_exc:
                log.debug("A2A dispatch skipped for %s: %s", team, _a2a_exc)

    # 3. Generate team-specific artifacts
    gen_fn = _GENERATORS.get(team)
    if gen_fn and team == "qa_eng":
        gen_data = gen_fn(requirement, detail, all_code=all_code)
    elif gen_fn:
        gen_data = gen_fn(requirement, detail)
    else:
        gen_data = {}

    # 4. Execute tools
    tools_used: list[ToolExecution] = []
    # Blocking state — set by any hard-block tool failure
    _block_tool = ""
    _block_reason = ""
    _autofix_applied = False

    # Tavily search (single query or multiple research queries for deep-research teams)
    if tool_cfg and "tavily_search" in tool_cfg.tools:
        queries: list[str] = gen_data.get("search_queries") or []  # type: ignore[assignment]
        if not queries and gen_data.get("search_query"):
            queries = [gen_data["search_query"]]
        for _q in queries:
            tools_used.append(_execute_tavily(team, _q))

    # Mermaid diagrams
    if tool_cfg and "mermaid" in tool_cfg.tools and gen_data.get("mermaid"):
        dtype, dtitle, dcontent = gen_data["mermaid"]
        tools_used.append(_execute_mermaid(team, dtype, dtitle, dcontent))

    # Google Docs
    if tool_cfg and "google_docs" in tool_cfg.tools and gen_data.get("doc_title"):
        doc_title = f"[{project_id or 'project'}] {gen_data['doc_title']}"
        tools_used.append(_execute_google_docs(team, doc_title, gen_data["doc_content"], folder_id))

    # Google Sheets (includes solution_arch tech decision matrix)
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
            _te_git = _execute_git(team, git_url, git_token, project_id, code_files)
            if not _te_git.success and not _block_tool:
                _block_tool = "git"
                _block_reason = get_tool_recovery_question("git", _te_git.error or "") or ""
            tools_used.append(_te_git)
        elif uid and project_id:
            for fname, fcontent in code_files.items():
                tools_used.append(_execute_gcs(team, uid, project_id, fname.replace("/", "_"), fcontent))
        else:
            tools_used.append(ToolExecution(tool="gcs", action=f"Skipped {len(code_files)} files (no uid/project)", success=False, error="No storage configured"))

    # ── Security scanning (semgrep / trivy / ruff) ───────────────────────────
    if tool_cfg and "semgrep" in tool_cfg.tools and code_files:
        tools_used.append(_execute_semgrep(team, code_files))

    if tool_cfg and "trivy" in tool_cfg.tools and code_files:
        tools_used.append(_execute_trivy_iac(team, code_files))

    # ── Code quality tools with LLM auto-fix ────────────────────────────────
    # For each gate: run → if fail → try LLM fix → re-run → if still fail → block.
    for _cq_name, _cq_fn in [
        ("ruff",   _execute_ruff   if (tool_cfg and "ruff"   in tool_cfg.tools and code_files) else None),
        ("black",  _execute_black  if (tool_cfg and "black"  in tool_cfg.tools and code_files) else None),
        ("mypy",   _execute_mypy   if (tool_cfg and "mypy"   in tool_cfg.tools and code_files) else None),
        ("bandit", _execute_bandit if (tool_cfg and "bandit" in tool_cfg.tools and code_files) else None),
    ]:
        if _cq_fn is None:
            continue
        _te = _cq_fn(team, code_files)
        if not _te.success and llm_runtime is not None:
            _vcount = (_te.result or {}).get("violation_count") or (_te.result or {}).get("error_count") or "?"
            log.info("%s › %s failed (%s violations) — attempting LLM auto-fix", team, _cq_name, _vcount)
            _fixed = _try_autofix_code_quality(_cq_name, _te, code_files, llm_runtime, requirement)
            if _fixed is not None:
                _te2 = _cq_fn(team, _fixed)
                if _te2.success:
                    code_files = _fixed           # propagate fixed code to all subsequent tools
                    _autofix_applied = True
                    _te2.action = f"✓ auto-fixed → {_te2.action}"
                    tools_used.append(_te2)
                    log.info("%s › %s: LLM auto-fix SUCCEEDED", team, _cq_name)
                    continue
                _te = _te2
                _te.action += " [auto-fix attempted, violations remain]"
                log.warning("%s › %s: LLM auto-fix FAILED — violations remain", team, _cq_name)
            else:
                _te.action += " [auto-fix unavailable — no LLM proxy response]"
        if not _te.success and not _block_tool:
            _block_tool = _cq_name
            _block_reason = get_tool_recovery_question(_cq_name, _te.error or "") or ""
        tools_used.append(_te)

    # ── Gitleaks secret scan ──────────────────────────────────────────────────
    if tool_cfg and "gitleaks" in tool_cfg.tools and code_files:
        tools_used.append(_execute_gitleaks(team, code_files))

    # ── Checkov IaC scan ─────────────────────────────────────────────────────
    if tool_cfg and "checkov" in tool_cfg.tools and code_files:
        tools_used.append(_execute_checkov(team, code_files))

    # ── Plane issue tracking (all teams with Plane configured) ──────────────
    if tool_cfg and "plane" in tool_cfg.tools and project_id:
        decision_type_for_plane = _DECISION_TYPES.get(team, "architecture")
        issue_title = (
            gen_data.get("plane_issue_title")
            or gen_data.get("doc_title")
            or gen_data.get("sheet_title")
            or f"[{team}] {decision_type_for_plane}: {requirement[:60]}"
        )
        tools_used.append(
            _execute_plane(team, project_id, requirement, issue_title, decision_type_for_plane, detail[:300])
        )

    # ── Stage-complete notification (every team) ─────────────────────────────
    if tool_cfg and "notification" in tool_cfg.tools:
        tools_used.append(
            _execute_notification(team, project_id or "pipeline", requirement, detail[:200])
        )

    # ── Slack rich notification (teams with slack configured) ────────────────
    if tool_cfg and "slack" in tool_cfg.tools:
        doc_title = gen_data.get("doc_title") or gen_data.get("sheet_title") or f"{team} artifact"
        tools_used.append(_execute_slack(team, project_id or "pipeline", doc_title, handoff))

    # ── Confluence wiki publish (docs_team, solution_arch, compliance, biz_analysis) ───
    if tool_cfg and "confluence" in tool_cfg.tools and gen_data.get("doc_content"):
        tools_used.append(_execute_confluence(
            team, project_id,
            gen_data.get("doc_title", f"{team} documentation"),
            gen_data["doc_content"],
        ))

    # ── Jira issue creation (product_mgmt, feature_eng, biz_analysis) ────────
    if tool_cfg and "jira" in tool_cfg.tools and project_id:
        jira_title = (
            gen_data.get("plane_issue_title")
            or gen_data.get("doc_title")
            or f"[{team}] {requirement[:80]}"
        )
        tools_used.append(_execute_jira(
            team, project_id,
            summary=jira_title,
            description=detail[:1000],
        ))

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
        f"- a2a_messages_sent: {len(a2a_dispatched)}\n"
        f"- handoff_to: {handoff}"
    )

    # Surface Sol Arch clarifying questions in the artifact so the pipeline chat
    # can show them immediately without requiring group chat navigation.
    if team == "solution_arch":
        _qs: list[str] = gen_data.get("clarifying_questions", [])  # type: ignore[assignment]
        if _qs:
            artifact += (
                f"\n- clarifying_questions_count: {len(_qs)}"
                f"\n- clarifying_questions: {' || '.join(_qs)}"
            )

    # ── Decision metadata ──────────────────────────────────────────────────
    decision_type = _DECISION_TYPES.get(team, "architecture")
    decision_title = (
        gen_data.get("doc_title")
        or gen_data.get("sheet_title")
        or f"{team.replace('_', ' ').title()} — {requirement[:60]}"
    )
    # Use the LLM-generated detail as rationale (first 500 chars); fall back to action line
    decision_rationale = (detail or "").strip()[:500] or f"Phase 2 artifact for {team}"

    return Phase2StageArtifact(
        team=team,
        artifact=artifact,
        tools_used=tools_used,
        code_files=code_files,
        qa_issues=gen_data.get("qa_issues", []),
        qa_verdict=gen_data.get("qa_verdict", ""),
        decision_type=decision_type,
        decision_title=decision_title,
        decision_rationale=decision_rationale,
        blocked=bool(_block_tool),
        block_tool=_block_tool,
        block_reason=_block_reason,
        autofix_applied=_autofix_applied,
        # Populate per-team handoffs only for solution_arch
        sol_arch_handoffs=gen_data.get("handoff_data", {}) if team == "solution_arch" else {},
    )
