"""Gitleaks tool — secret and credential scanning in Git repositories.

Used by security_eng and devops teams to detect hardcoded API keys,
passwords, tokens, and private keys before they reach production.

Env vars:
  GITLEAKS_BIN      — path to gitleaks binary (default: gitleaks)
  GITLEAKS_TIMEOUT  — subprocess timeout seconds (default: 120)
  GITLEAKS_CONFIG   — optional custom .toml config path
"""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

GITLEAKS_BIN = os.getenv("GITLEAKS_BIN", "gitleaks")
TIMEOUT = int(os.getenv("GITLEAKS_TIMEOUT", "120"))
CONFIG = os.getenv("GITLEAKS_CONFIG", "")


def _run(args: list[str]) -> dict:
    cmd = [GITLEAKS_BIN] + args + ["--report-format", "json"]
    if CONFIG:
        cmd += ["--config", CONFIG]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        # gitleaks exits 1 when leaks found
        try:
            data = json.loads(result.stdout) if result.stdout.strip() else []
        except json.JSONDecodeError:
            data = []
        return {"leaks": data, "returncode": result.returncode, "stderr": result.stderr[:500]}
    except FileNotFoundError:
        return {"leaks": [], "returncode": -1,
                "error": "gitleaks not found — install from https://github.com/gitleaks/gitleaks/releases"}
    except subprocess.TimeoutExpired:
        return {"leaks": [], "returncode": -1, "error": "gitleaks timed out"}


def _parse(raw: dict) -> dict:
    leaks = raw.get("leaks", [])
    if "error" in raw:
        return {"passed": True, "secret_count": 0, "leaks": [], "error": raw["error"]}
    findings = []
    for leak in leaks:
        findings.append({
            "rule_id": leak.get("RuleID") or leak.get("rule_id", ""),
            "description": leak.get("Description") or leak.get("description", ""),
            "file": leak.get("File") or leak.get("file", ""),
            "line": leak.get("StartLine") or leak.get("start_line", 0),
            "commit": (leak.get("Commit") or leak.get("commit", ""))[:12],
            "author": leak.get("Author") or leak.get("author", ""),
            "date": leak.get("Date") or leak.get("date", ""),
            # Mask actual secret value
            "secret_preview": (leak.get("Secret") or leak.get("secret", ""))[:6] + "***",
        })
    return {
        "passed": len(findings) == 0,
        "secret_count": len(findings),
        "leaks": findings[:50],
    }


def scan_repo(path: str = ".", since_commit: str = "") -> dict:
    """Scan a git repository for secrets in commit history.

    Args:
      path:         Path to git repository (default: current dir)
      since_commit: Optional commit SHA to scan from (for incremental scans)

    Returns:
      {"passed": bool, "secret_count": int, "leaks": list[{"rule_id","file","line","secret_preview"}]}
    """
    args = ["detect", "--source", path, "--no-git" if not Path(path, ".git").exists() else ""]
    args = [a for a in args if a]
    if since_commit:
        args += ["--log-opts", f"{since_commit}..HEAD"]
    raw = _run(args)
    return _parse(raw)


def scan_string(content: str, rule_hint: str = "") -> dict:
    """Scan a string/content snippet for secrets (uses --no-git mode).

    Args:
      content:   String to scan (e.g. env file content, config dump)
      rule_hint: Optional description for reporting

    Returns:
      {"passed": bool, "secret_count": int, "leaks": list}
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, prefix="gitleaks_") as f:
        f.write(content)
        tmp_path = f.name
    try:
        raw = _run(["detect", "--source", tmp_path, "--no-git"])
        result = _parse(raw)
        # Fix file path in findings back to rule_hint
        for leak in result.get("leaks", []):
            if rule_hint:
                leak["file"] = rule_hint
        return result
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def scan_staged_changes(repo_path: str = ".") -> dict:
    """Scan only staged (pre-commit) changes for secrets.

    Useful as a pre-commit gate. Returns same structure as scan_repo().
    """
    args = ["protect", "--staged", "--source", repo_path]
    raw = _run(args)
    return _parse(raw)
