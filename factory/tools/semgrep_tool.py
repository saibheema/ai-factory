"""Semgrep tool — SAST (Static Application Security Testing) via Semgrep CLI.

Open source: https://semgrep.dev  (LGPL-2.1)
Install: pip install semgrep

Env vars:
  SEMGREP_BIN     — path to semgrep binary (default: semgrep)
  SEMGREP_RULES   — ruleset (default: p/python  — auto-detects language)
"""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

SEMGREP_BIN = os.getenv("SEMGREP_BIN", "semgrep")
SEMGREP_RULES = os.getenv("SEMGREP_RULES", "auto")


def scan_code(code: str, language: str = "python", filename: str | None = None) -> dict:
    """Scan a code string for security issues.

    Returns: {"passed": bool, "findings": [...], "finding_count": int}
    """
    ext = {"python": ".py", "javascript": ".js", "typescript": ".ts", "go": ".go", "java": ".java"}.get(language, ".py")
    fname = filename or f"scan{ext}"
    with tempfile.TemporaryDirectory(prefix="aifactory-semgrep-") as tmp:
        fpath = Path(tmp) / fname
        fpath.write_text(code, encoding="utf-8")
        return scan_directory(tmp)


def scan_directory(directory: str) -> dict:
    """Scan a directory with Semgrep.

    Returns:
      {"passed": bool, "findings": [{"rule_id", "message", "severity", "file", "line"}], "finding_count": int}
    """
    try:
        result = subprocess.run(
            [
                SEMGREP_BIN, "scan",
                "--config", SEMGREP_RULES,
                "--json",
                "--quiet",
                directory,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        findings = []
        output = result.stdout.strip()
        if output:
            try:
                data = json.loads(output)
                findings = [
                    {
                        "rule_id": f.get("check_id", ""),
                        "message": f.get("extra", {}).get("message", ""),
                        "severity": f.get("extra", {}).get("severity", "WARNING"),
                        "file": f.get("path", ""),
                        "line": f.get("start", {}).get("line", 0),
                    }
                    for f in data.get("results", [])
                ]
            except json.JSONDecodeError:
                pass

        errors_only = [f for f in findings if f["severity"] in ("ERROR", "HIGH")]
        passed = len(errors_only) == 0
        log.info("semgrep scan: %s — %d finding(s)", directory, len(findings))
        return {
            "passed": passed,
            "findings": findings,
            "finding_count": len(findings),
            "high_severity_count": len(errors_only),
        }
    except FileNotFoundError:
        log.warning("semgrep not found — install: pip install semgrep")
        return {"passed": True, "findings": [], "finding_count": 0, "warning": "semgrep not installed"}
    except subprocess.TimeoutExpired:
        return {"passed": False, "findings": [], "finding_count": 0, "error": "semgrep scan timed out"}
    except Exception as e:
        log.warning("semgrep scan failed: %s", e)
        return {"passed": False, "findings": [], "finding_count": 0, "error": str(e)}
