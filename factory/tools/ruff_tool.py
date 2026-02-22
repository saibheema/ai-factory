"""Ruff linting tool — fast Python linter via CLI subprocess.

Env vars:
  RUFF_BIN  — path to ruff binary (default: ruff from PATH)
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

RUFF_BIN = os.getenv("RUFF_BIN", "ruff")


def lint_code(code: str, filename: str = "code.py") -> dict:
    """Lint a Python code string with ruff.

    Returns: {"passed": bool, "violations": [{"line", "col", "code", "message"}], "violation_count": int}
    """
    with tempfile.TemporaryDirectory(prefix="aifactory-ruff-") as tmp:
        fpath = Path(tmp) / filename
        fpath.write_text(code, encoding="utf-8")
        return lint_file(str(fpath))


def lint_file(filepath: str) -> dict:
    """Lint a file path with ruff.

    Returns: {"passed": bool, "violations": [...], "violation_count": int, "filepath": str}
    """
    try:
        result = subprocess.run(
            [RUFF_BIN, "check", "--output-format=json", filepath],
            capture_output=True,
            text=True,
            timeout=30,
        )
        import json
        violations = []
        if result.stdout.strip():
            raw = json.loads(result.stdout)
            violations = [
                {
                    "line": v.get("location", {}).get("row", 0),
                    "col": v.get("location", {}).get("column", 0),
                    "code": v.get("code", ""),
                    "message": v.get("message", ""),
                    "fix_available": v.get("fix") is not None,
                }
                for v in raw
            ]
        passed = len(violations) == 0
        log.info("ruff lint: %s — %d violation(s)", filepath, len(violations))
        return {"passed": passed, "violations": violations, "violation_count": len(violations), "filepath": filepath}
    except FileNotFoundError:
        log.warning("ruff not found at '%s' — install with: pip install ruff", RUFF_BIN)
        return {"passed": True, "violations": [], "violation_count": 0, "warning": "ruff not installed"}
    except Exception as e:
        log.warning("ruff lint failed: %s", e)
        return {"passed": False, "violations": [], "violation_count": 0, "error": str(e)}


def lint_directory(directory: str) -> dict:
    """Lint an entire directory. Returns aggregated results."""
    try:
        result = subprocess.run(
            [RUFF_BIN, "check", "--output-format=json", directory],
            capture_output=True,
            text=True,
            timeout=60,
        )
        import json
        violations = []
        if result.stdout.strip():
            raw = json.loads(result.stdout)
            violations = [
                {
                    "file": v.get("filename", ""),
                    "line": v.get("location", {}).get("row", 0),
                    "code": v.get("code", ""),
                    "message": v.get("message", ""),
                }
                for v in raw
            ]
        passed = len(violations) == 0
        log.info("ruff dir lint: %s — %d violation(s)", directory, len(violations))
        return {"passed": passed, "violations": violations, "violation_count": len(violations), "directory": directory}
    except FileNotFoundError:
        return {"passed": True, "violations": [], "violation_count": 0, "warning": "ruff not installed"}
    except Exception as e:
        return {"passed": False, "violations": [], "error": str(e)}
