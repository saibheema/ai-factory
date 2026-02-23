"""Black tool — opinionated Python code formatter.

Used by backend_eng and frontend_eng (Python microservices)
to enforce consistent formatting and produce diff reports.

Env vars:
  BLACK_BIN      — path to black binary (default: black)
  BLACK_TIMEOUT  — subprocess timeout seconds (default: 30)
  BLACK_LINE_LEN — max line length (default: 88)
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

BLACK_BIN = os.getenv("BLACK_BIN", "black")
TIMEOUT = int(os.getenv("BLACK_TIMEOUT", "30"))
LINE_LEN = int(os.getenv("BLACK_LINE_LEN", "88"))


def _run(args: list[str]) -> tuple[int, str, str]:
    cmd = [BLACK_BIN, f"--line-length={LINE_LEN}"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return -1, "", "black not found — install with: pip install black"
    except subprocess.TimeoutExpired:
        return -1, "", "black timed out"


def format_code(code: str, filename: str = "code.py") -> dict:
    """Format a Python code string with black.

    Args:
      code:     Python source code
      filename: Virtual filename for reporting

    Returns:
      {"success": bool, "reformatted": bool, "formatted_code": str, "error": str|None}
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp = f.name
    try:
        rc, stdout, stderr = _run([tmp])
        if rc == -1:
            return {"success": False, "reformatted": False, "formatted_code": code, "error": stderr}
        formatted = Path(tmp).read_text()
        reformatted = formatted != code
        return {"success": True, "reformatted": reformatted, "formatted_code": formatted, "error": None}
    finally:
        Path(tmp).unlink(missing_ok=True)


def check_formatting(code: str, filename: str = "code.py") -> dict:
    """Check whether code is already black-formatted (dry run, no changes).

    Args:
      code:     Python source code
      filename: Virtual filename for reporting

    Returns:
      {"passed": bool, "reformatted_needed": bool, "diff": str, "error": str|None}
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp = f.name
    try:
        rc, stdout, stderr = _run(["--check", "--diff", tmp])
        if rc == -1:
            return {"passed": True, "reformatted_needed": False, "diff": "", "error": stderr}
        # black exits 1 if reformatting needed, 0 if already formatted
        return {
            "passed": rc == 0,
            "reformatted_needed": rc == 1,
            "diff": stderr[:3000],  # black prints diff to stderr
            "error": None,
        }
    finally:
        Path(tmp).unlink(missing_ok=True)


def format_file(filepath: str) -> dict:
    """Format a Python file in-place.

    Returns:
      {"success": bool, "reformatted": bool, "error": str|None}
    """
    rc, stdout, stderr = _run([filepath])
    if rc == -1:
        return {"success": False, "reformatted": False, "error": stderr}
    reformatted = "reformatted" in stderr
    return {"success": True, "reformatted": reformatted, "error": None}


def format_directory(path: str, check_only: bool = False) -> dict:
    """Format or check all Python files in a directory.

    Args:
      path:       Directory path
      check_only: If True, only check without modifying

    Returns:
      {"success": bool, "files_reformatted": int, "error": str|None}
    """
    args = [path]
    if check_only:
        args.insert(0, "--check")
    rc, stdout, stderr = _run(args)
    if rc == -1:
        return {"success": False, "files_reformatted": 0, "error": stderr}

    import re
    reformatted = len(re.findall(r"reformatted", stderr))
    return {
        "success": rc == 0 or not check_only,
        "files_reformatted": reformatted,
        "check_only": check_only,
        "output": stderr[:1000],
        "error": None if rc in (0, 1) else stderr,
    }
