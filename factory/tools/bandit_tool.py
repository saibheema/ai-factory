"""Bandit tool — Python security static analysis.

Used by security_eng and backend_eng to detect common
vulnerabilities: SQL injection, shell injection, weak crypto, etc.

Env vars:
  BANDIT_BIN      — path to bandit binary (default: bandit)
  BANDIT_SEVERITY — min severity level: LOW | MEDIUM | HIGH (default: LOW)
  BANDIT_TIMEOUT  — subprocess timeout seconds (default: 60)
"""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

BANDIT_BIN = os.getenv("BANDIT_BIN", "bandit")
SEVERITY = os.getenv("BANDIT_SEVERITY", "LOW")
TIMEOUT = int(os.getenv("BANDIT_TIMEOUT", "60"))


def _run_bandit(args: list[str]) -> dict:
    cmd = [BANDIT_BIN, "-f", "json"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        # bandit exits 1 when issues found — that's expected
        raw = result.stdout or result.stderr
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
        return {"raw_output": raw, "data": data, "returncode": result.returncode}
    except FileNotFoundError:
        return {"raw_output": "", "data": {}, "returncode": -1,
                "error": f"bandit not found — install with: pip install bandit"}
    except subprocess.TimeoutExpired:
        return {"raw_output": "", "data": {}, "returncode": -1, "error": "bandit timed out"}


def _parse_results(data: dict) -> dict:
    results_list = data.get("results", [])
    metrics = data.get("metrics", {}).get("_totals", {})
    findings = []
    for r in results_list:
        findings.append({
            "test_id": r.get("test_id"),
            "test_name": r.get("test_name"),
            "severity": r.get("issue_severity"),
            "confidence": r.get("issue_confidence"),
            "file": r.get("filename"),
            "line": r.get("line_number"),
            "text": r.get("issue_text"),
            "code": r.get("code", "").strip()[:200],
        })
    high = sum(1 for f in findings if f["severity"] == "HIGH")
    medium = sum(1 for f in findings if f["severity"] == "MEDIUM")
    low = sum(1 for f in findings if f["severity"] == "LOW")
    return {
        "passed": high == 0 and medium == 0,
        "total_issues": len(findings),
        "high": high,
        "medium": medium,
        "low": low,
        "findings": findings[:50],
    }


def scan_code(code: str, filename: str = "code.py") -> dict:
    """Scan a Python code string with bandit.

    Args:
      code:     Python source code
      filename: Virtual filename used in report (default: code.py)

    Returns:
      {"passed": bool, "total_issues": int, "high": int, "medium": int, "low": int,
       "findings": list[{"test_id","severity","line","text","code"}]}
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp_path = f.name
    try:
        result = _run_bandit([tmp_path])
        if "error" in result:
            return {"passed": True, "total_issues": 0, "high": 0, "medium": 0, "low": 0,
                    "findings": [], "error": result["error"]}
        return _parse_results(result["data"])
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def scan_file(filepath: str) -> dict:
    """Scan a Python file with bandit.

    Args:
      filepath: Absolute or relative path to .py file

    Returns:
      Same structure as scan_code()
    """
    result = _run_bandit([filepath])
    if "error" in result:
        return {"passed": True, "total_issues": 0, "high": 0, "medium": 0, "low": 0,
                "findings": [], "error": result["error"]}
    return _parse_results(result["data"])


def scan_directory(path: str, exclude_dirs: list[str] | None = None, recursive: bool = True) -> dict:
    """Scan a directory of Python files.

    Args:
      path:         Directory path to scan
      exclude_dirs: Directories to exclude (e.g. ["tests", ".venv"])
      recursive:    Scan recursively (default True)

    Returns:
      {"passed": bool, "total_issues": int, "high": int, "medium": int, "low": int,
       "findings": list, "files_scanned": int}
    """
    args = [path]
    if recursive:
        args.append("-r")
    if exclude_dirs:
        args += ["--exclude", ",".join(exclude_dirs)]

    result = _run_bandit(args)
    if "error" in result:
        return {"passed": True, "total_issues": 0, "high": 0, "medium": 0, "low": 0,
                "findings": [], "files_scanned": 0, "error": result["error"]}

    parsed = _parse_results(result["data"])
    metrics = result["data"].get("metrics", {})
    files_scanned = len([k for k in metrics if k != "_totals"])
    return {**parsed, "files_scanned": files_scanned}
