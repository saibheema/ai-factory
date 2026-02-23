"""Mypy tool — static type checking for Python.

Used by backend_eng, data_eng, and ml_eng to enforce type safety
and catch runtime errors at analysis time.

Env vars:
  MYPY_BIN      — path to mypy binary (default: mypy)
  MYPY_TIMEOUT  — subprocess timeout seconds (default: 120)
  MYPY_CONFIG   — optional mypy.ini or pyproject.toml path
"""

import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

MYPY_BIN = os.getenv("MYPY_BIN", "mypy")
TIMEOUT = int(os.getenv("MYPY_TIMEOUT", "120"))
CONFIG = os.getenv("MYPY_CONFIG", "")

# Regex to parse mypy output lines:  file.py:10: error: ...
_LINE_RE = re.compile(r"^(.+?):(\d+):\s+(error|warning|note):\s+(.+)$")


def _run(args: list[str], code: str = "") -> dict:
    """Run mypy and return parsed results."""
    cmd = [MYPY_BIN, "--output", "json"] + args
    if CONFIG:
        cmd += ["--config-file", CONFIG]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        errors = []
        for line in (result.stdout + result.stderr).splitlines():
            try:
                # mypy --output json emits JSON objects per line
                obj = json.loads(line)
                errors.append({
                    "file": obj.get("file", ""),
                    "line": obj.get("line", 0),
                    "column": obj.get("column", 0),
                    "severity": obj.get("severity", "error"),
                    "message": obj.get("message", ""),
                    "code": obj.get("code", ""),
                })
            except json.JSONDecodeError:
                m = _LINE_RE.match(line)
                if m:
                    errors.append({
                        "file": m.group(1),
                        "line": int(m.group(2)),
                        "severity": m.group(3),
                        "message": m.group(4),
                        "column": 0,
                        "code": "",
                    })
        actual_errors = [e for e in errors if e["severity"] == "error"]
        return {
            "passed": result.returncode == 0,
            "error_count": len(actual_errors),
            "warning_count": len([e for e in errors if e["severity"] == "warning"]),
            "errors": actual_errors[:100],
            "raw_output": (result.stdout + result.stderr)[:2000],
        }
    except FileNotFoundError:
        return {"passed": True, "error_count": 0, "warning_count": 0, "errors": [],
                "error": "mypy not found — install with: pip install mypy"}
    except subprocess.TimeoutExpired:
        return {"passed": False, "error_count": -1, "warning_count": 0, "errors": [],
                "error": "mypy timed out"}


def check_code(code: str, filename: str = "code.py", strict: bool = False) -> dict:
    """Type-check a Python code string.

    Args:
      code:     Python source code
      filename: Virtual filename for reporting
      strict:   Enable mypy --strict mode

    Returns:
      {"passed": bool, "error_count": int, "errors": list[{"file","line","severity","message"}]}
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp = f.name
    try:
        args = [tmp]
        if strict:
            args.append("--strict")
        result = _run(args)
        # Replace temp path with virtual filename
        for e in result.get("errors", []):
            e["file"] = filename
        return result
    finally:
        Path(tmp).unlink(missing_ok=True)


def check_file(filepath: str, strict: bool = False) -> dict:
    """Type-check a Python file.

    Args:
      filepath: Absolute path to .py file
      strict:   Enable mypy --strict mode

    Returns:
      Same structure as check_code()
    """
    args = [filepath]
    if strict:
        args.append("--strict")
    return _run(args)


def check_directory(path: str, strict: bool = False, ignore_missing_imports: bool = True) -> dict:
    """Type-check a Python package or directory.

    Args:
      path:                    Directory path
      strict:                  Enable --strict mode
      ignore_missing_imports:  Silence missing stub warnings (default: True)

    Returns:
      {"passed": bool, "error_count": int, "warning_count": int, "errors": list}
    """
    args = [path]
    if strict:
        args.append("--strict")
    if ignore_missing_imports:
        args.append("--ignore-missing-imports")
    return _run(args)
