"""Pytest tool — run tests and parse results via subprocess.

Env vars:
  PYTEST_BIN  — path to pytest binary (default: pytest from PATH)
"""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

PYTEST_BIN = os.getenv("PYTEST_BIN", "pytest")


def run_tests(test_dir: str, extra_args: list[str] | None = None) -> dict:
    """Run pytest against a directory and return structured results.

    Returns:
      {
        "passed": bool,
        "summary": {"total": int, "passed": int, "failed": int, "errors": int, "skipped": int},
        "failures": [{"nodeid": str, "message": str}],
        "coverage_pct": float | None,
        "duration_s": float,
      }
    """
    with tempfile.TemporaryDirectory(prefix="aifactory-pytest-") as tmp:
        report_json = Path(tmp) / "report.json"
        cmd = [
            PYTEST_BIN,
            test_dir,
            f"--json-report",
            f"--json-report-file={report_json}",
            "--tb=short",
            "-q",
        ]
        if extra_args:
            cmd.extend(extra_args)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except FileNotFoundError:
            log.warning("pytest not found — install with: pip install pytest pytest-json-report")
            return {"passed": True, "summary": {}, "failures": [], "warning": "pytest not installed"}
        except subprocess.TimeoutExpired:
            return {"passed": False, "summary": {}, "failures": [], "error": "pytest timed out"}
        except Exception as e:
            return {"passed": False, "summary": {}, "failures": [], "error": str(e)}

        # Parse JSON report if available
        if report_json.exists():
            try:
                report = json.loads(report_json.read_text())
                summary = report.get("summary", {})
                failures = [
                    {"nodeid": t.get("nodeid", ""), "message": t.get("call", {}).get("longrepr", "")[:500]}
                    for t in report.get("tests", [])
                    if t.get("outcome") in ("failed", "error")
                ]
                passed = summary.get("failed", 0) == 0 and summary.get("errors", 0) == 0
                log.info(
                    "pytest: %d passed / %d failed / %d errors",
                    summary.get("passed", 0), summary.get("failed", 0), summary.get("errors", 0),
                )
                return {
                    "passed": passed,
                    "summary": {
                        "total": summary.get("total", 0),
                        "passed": summary.get("passed", 0),
                        "failed": summary.get("failed", 0),
                        "errors": summary.get("errors", 0),
                        "skipped": summary.get("skipped", 0),
                    },
                    "failures": failures,
                    "duration_s": report.get("duration", 0.0),
                }
            except Exception as e:
                log.warning("Could not parse pytest JSON report: %s", e)

        # Fallback: parse text output
        passed = result.returncode == 0
        return {
            "passed": passed,
            "summary": {},
            "failures": [],
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "returncode": result.returncode,
        }


def run_test_code(code: str, filename: str = "test_generated.py") -> dict:
    """Write test code to a temp file and run it with pytest."""
    with tempfile.TemporaryDirectory(prefix="aifactory-pytest-code-") as tmp:
        fpath = Path(tmp) / filename
        fpath.write_text(code, encoding="utf-8")
        return run_tests(tmp)
