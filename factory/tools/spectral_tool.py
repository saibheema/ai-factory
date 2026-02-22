"""Spectral tool — OpenAPI spec linting via Spectral CLI.

Open source: https://github.com/stoplightio/spectral  (Apache-2.0)
Install: npm install -g @stoplight/spectral-cli

Env vars:
  SPECTRAL_BIN     — path to spectral binary (default: spectral)
  SPECTRAL_RULESET — ruleset file path or URL (default: @stoplight/spectral-oas)
"""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

SPECTRAL_BIN = os.getenv("SPECTRAL_BIN", "spectral")
SPECTRAL_RULESET = os.getenv("SPECTRAL_RULESET", "@stoplight/spectral-oas")


def lint_spec(spec_content: str, filename: str = "openapi.yaml") -> dict:
    """Lint an OpenAPI YAML/JSON string with Spectral.

    Returns:
      {"passed": bool, "violations": [{"code", "message", "severity", "path", "line"}], "violation_count": int}
    """
    with tempfile.TemporaryDirectory(prefix="aifactory-spectral-") as tmp:
        fpath = Path(tmp) / filename
        fpath.write_text(spec_content, encoding="utf-8")
        return lint_file(str(fpath))


def lint_file(filepath: str) -> dict:
    """Lint an OpenAPI file with Spectral.

    Returns: {"passed": bool, "violations": [...], "violation_count": int}
    """
    try:
        result = subprocess.run(
            [SPECTRAL_BIN, "lint", filepath, "--format", "json", "--ruleset", SPECTRAL_RULESET],
            capture_output=True,
            text=True,
            timeout=60,
        )
        violations = []
        output = result.stdout.strip() or result.stderr.strip()
        if output:
            try:
                raw = json.loads(output)
                violations = [
                    {
                        "code": v.get("code", ""),
                        "message": v.get("message", ""),
                        "severity": _severity(v.get("severity", 1)),
                        "path": ".".join(str(p) for p in v.get("path", [])),
                        "line": v.get("range", {}).get("start", {}).get("line", 0),
                    }
                    for v in (raw if isinstance(raw, list) else [])
                ]
            except json.JSONDecodeError:
                pass

        # Only errors (severity 0) count as failures
        errors = [v for v in violations if v["severity"] == "error"]
        passed = len(errors) == 0
        log.info("spectral lint: %s — %d violations (%d errors)", filepath, len(violations), len(errors))
        return {
            "passed": passed,
            "violations": violations,
            "violation_count": len(violations),
            "error_count": len(errors),
        }
    except FileNotFoundError:
        log.warning("spectral not found — install: npm install -g @stoplight/spectral-cli")
        return {"passed": True, "violations": [], "violation_count": 0, "warning": "spectral not installed"}
    except Exception as e:
        log.warning("spectral lint failed: %s", e)
        return {"passed": False, "violations": [], "violation_count": 0, "error": str(e)}


def _severity(level: int) -> str:
    return {0: "error", 1: "warning", 2: "info", 3: "hint"}.get(level, "warning")
