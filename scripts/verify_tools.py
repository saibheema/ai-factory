"""Verify all factory/tools files: syntax, imports, and basic runtime checks."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

results = {}
PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "


# ── 1. Registry ───────────────────────────────────────────────────────────────
try:
    from factory.tools.registry import all_tools
    tools = all_tools().list_tools()
    results["registry"] = (PASS, f"{len(tools)} tools: {', '.join(tools.keys())}")
except Exception as e:
    results["registry"] = (FAIL, str(e))


# ── 2. Team Tools ─────────────────────────────────────────────────────────────
try:
    from factory.tools.team_tools import get_all_team_tools, get_team_tool_summary
    teams = get_all_team_tools()
    summary = get_team_tool_summary()
    total_assignments = sum(len(t["tools"]) for t in summary)
    # Check every team has notification
    missing_notify = [t["team"] for t in summary if "notification" not in t["tools"]]
    note = f"{len(teams)} teams, {total_assignments} total assignments"
    if missing_notify:
        note += f" | MISSING notification: {missing_notify}"
    results["team_tools"] = (PASS, note)
except Exception as e:
    results["team_tools"] = (FAIL, str(e))


# ── 3. Mermaid (pure Python, no external deps) ───────────────────────────────
try:
    from factory.tools.mermaid_tool import render_diagram
    r = render_diagram("flowchart", "Test Diagram", "flowchart TD\n  A-->B\n  B-->C")
    assert "mermaid" in r
    assert "preview_url" in r
    assert r["preview_url"].startswith("https://mermaid.live")
    results["mermaid"] = (PASS, f"preview_url: {r['preview_url'][:60]}...")
except Exception as e:
    results["mermaid"] = (FAIL, str(e))


# ── 4. Sandbox ────────────────────────────────────────────────────────────────
try:
    from factory.tools.sandbox_tool import execute_python, validate_python_syntax, execute_shell

    # exec test
    r = execute_python('print("sandbox-ok")')
    assert r["stdout"].strip() == "sandbox-ok", f"got: {r['stdout']!r}"

    # syntax valid
    v = validate_python_syntax("x = 1 + 2\nprint(x)")
    assert v["valid"] is True

    # syntax invalid
    bad = validate_python_syntax("def broken(:")
    assert bad["valid"] is False

    # shell exec
    sh = execute_shell("echo shell-ok")
    assert "shell-ok" in sh["stdout"]

    results["sandbox"] = (PASS, "exec + syntax-check + shell all pass")
except Exception as e:
    results["sandbox"] = (FAIL, str(e))


# ── 5. Ruff ──────────────────────────────────────────────────────────────────
try:
    from factory.tools.ruff_tool import lint_code
    # clean code
    clean = lint_code("x = 1\nprint(x)\n", "clean.py")
    # code with issues
    dirty = lint_code("import os\nimport sys\nx=1\n", "dirty.py")
    if "warning" in clean:
        results["ruff"] = (WARN, clean["warning"])
    else:
        results["ruff"] = (PASS, f"clean={clean['violation_count']} violations | dirty={dirty['violation_count']} violations")
except Exception as e:
    results["ruff"] = (FAIL, str(e))


# ── 6. Pytest ─────────────────────────────────────────────────────────────────
try:
    from factory.tools.pytest_tool import run_test_code
    r = run_test_code("def test_one():\n    assert 1 + 1 == 2\n\ndef test_two():\n    assert 'a' in 'abc'\n")
    if "warning" in r:
        results["pytest"] = (WARN, r["warning"])
    else:
        s = r.get("summary", {})
        results["pytest"] = (
            PASS if r["passed"] else FAIL,
            f"passed={s.get('passed', '?')} failed={s.get('failed', '?')} total={s.get('total', '?')}"
        )
except Exception as e:
    results["pytest"] = (FAIL, str(e))


# ── 7. Notification ──────────────────────────────────────────────────────────
try:
    from factory.tools.notification_tool import notify, notify_team_complete, notify_error
    r = notify("Verify Alert", "Tool verification ping", tags=["verify", "test"])
    # ntfy.sh may or may not be reachable — just check no exception
    results["notification"] = (PASS, f"channels={r['channels']} errors={r['errors']}")
except Exception as e:
    results["notification"] = (FAIL, str(e))


# ── 8. GitHub Tool ───────────────────────────────────────────────────────────
try:
    from factory.tools.github_tool import (
        create_repo, get_repo, create_issue, list_issues,
        create_pull_request, list_pull_requests, ensure_labels,
    )
    results["github_tool"] = (PASS, "all 7 functions importable (GITHUB_TOKEN needed for live calls)")
except Exception as e:
    results["github_tool"] = (FAIL, str(e))


# ── 9. Plane Tool ─────────────────────────────────────────────────────────────
try:
    from factory.tools.plane_tool import (
        create_project, get_or_create_project,
        create_issue, list_issues, update_issue_state, create_cycle,
    )
    results["plane_tool"] = (PASS, "all 6 functions importable (PLANE_API_KEY + server needed)")
except Exception as e:
    results["plane_tool"] = (FAIL, str(e))


# ── 10. Spectral Tool ─────────────────────────────────────────────────────────
try:
    from factory.tools.spectral_tool import lint_spec, lint_file
    # Call with empty spec — will gracefully return warning if CLI missing
    r = lint_spec("openapi: '3.0.0'\ninfo:\n  title: Test\n  version: '1.0'\npaths: {}\n")
    assert "passed" in r
    if "warning" in r:
        results["spectral_tool"] = (WARN, r["warning"])
    else:
        results["spectral_tool"] = (PASS, f"violations={r['violation_count']}")
except Exception as e:
    results["spectral_tool"] = (FAIL, str(e))


# ── 11. Semgrep Tool ──────────────────────────────────────────────────────────
try:
    from factory.tools.semgrep_tool import scan_code, scan_directory
    r = scan_code("import os\npassword = 'hardcoded'\n", language="python")
    assert "passed" in r
    if "warning" in r:
        results["semgrep_tool"] = (WARN, r["warning"])
    else:
        results["semgrep_tool"] = (PASS, f"findings={r['finding_count']} high={r['high_severity_count']}")
except Exception as e:
    results["semgrep_tool"] = (FAIL, str(e))


# ── 12. Trivy Tool ────────────────────────────────────────────────────────────
try:
    from factory.tools.trivy_tool import scan_image, scan_filesystem, scan_iac, scan_secrets
    results["trivy_tool"] = (PASS, "all 4 functions importable (trivy CLI needed for live calls)")
except Exception as e:
    results["trivy_tool"] = (FAIL, str(e))


# ── 13. MLflow Tool ───────────────────────────────────────────────────────────
try:
    from factory.tools.mlflow_tool import (
        create_experiment, log_run, register_model, list_models,
    )
    results["mlflow_tool"] = (PASS, "all 4 functions importable (mlflow server needed for live calls)")
except Exception as e:
    results["mlflow_tool"] = (FAIL, str(e))


# ── 14. GCS Tool ──────────────────────────────────────────────────────────────
try:
    from factory.tools.gcs_tool import upload_artifact, upload_json
    results["gcs_tool"] = (PASS, "importable (GCP credentials needed for live calls)")
except Exception as e:
    results["gcs_tool"] = (FAIL, str(e))


# ── 15. Git Tool ──────────────────────────────────────────────────────────────
try:
    from factory.tools.git_tool import push_files
    results["git_tool"] = (PASS, "importable (git + token needed for live calls)")
except Exception as e:
    results["git_tool"] = (FAIL, str(e))


# ── 16. Google Docs Tool ──────────────────────────────────────────────────────
try:
    from factory.tools.google_docs_tool import create_document, append_to_document
    results["google_docs"] = (PASS, "importable (GCP credentials needed for live calls)")
except Exception as e:
    results["google_docs"] = (FAIL, str(e))


# ── 17. Google Sheets Tool ────────────────────────────────────────────────────
try:
    from factory.tools.google_sheets_tool import create_spreadsheet
    results["google_sheets"] = (PASS, "importable (GCP credentials needed for live calls)")
except Exception as e:
    results["google_sheets"] = (FAIL, str(e))


# ── 18. Google Drive Tool ─────────────────────────────────────────────────────
try:
    from factory.tools.google_drive_tool import ensure_project_folder, share_with_user
    results["google_drive"] = (PASS, "importable (GCP credentials needed for live calls)")
except Exception as e:
    results["google_drive"] = (FAIL, str(e))


# ── 19. Tavily Tool ───────────────────────────────────────────────────────────
try:
    from factory.tools.tavily_tool import web_search
    # No API key — should return graceful empty result, not raise
    r = web_search("test query")
    assert "results" in r
    if not r["results"]:
        results["tavily_tool"] = (WARN, "TAVILY_API_KEY not set — graceful fallback confirmed")
    else:
        results["tavily_tool"] = (PASS, f"{len(r['results'])} results returned")
except Exception as e:
    results["tavily_tool"] = (FAIL, str(e))


# ── Print Results ─────────────────────────────────────────────────────────────
print()
print("═" * 70)
print("  AI FACTORY — TOOL VERIFICATION REPORT")
print("═" * 70)
ok_count = fail_count = warn_count = 0
for name, (status, msg) in results.items():
    bar = msg[:65] + "…" if len(msg) > 65 else msg
    print(f"  {status}  {name:<22} {bar}")
    if status == PASS:
        ok_count += 1
    elif status == WARN:
        warn_count += 1
    else:
        fail_count += 1
print("─" * 70)
print(f"  TOTAL: {len(results)} tools  |  ✅ {ok_count} pass  |  ⚠️  {warn_count} warn  |  ❌ {fail_count} fail")
print("═" * 70)

if fail_count > 0:
    sys.exit(1)
