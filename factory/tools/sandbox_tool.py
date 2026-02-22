"""Sandbox tool — execute code in an isolated subprocess with timeout + resource limits.

Safe execution for agent-generated code. No network access. Timeout enforced.

Env vars:
  SANDBOX_TIMEOUT  — max seconds per execution (default: 15)
  SANDBOX_DOCKER   — if "1", run inside a Docker container (default: subprocess)
"""

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", "15"))
USE_DOCKER = os.getenv("SANDBOX_DOCKER", "0") == "1"
DOCKER_IMAGE = os.getenv("SANDBOX_DOCKER_IMAGE", "python:3.11-slim")


def execute_python(code: str, stdin: str = "") -> dict:
    """Execute a Python code string in an isolated subprocess.

    Returns:
      {"success": bool, "stdout": str, "stderr": str, "returncode": int, "timed_out": bool}
    """
    with tempfile.TemporaryDirectory(prefix="aifactory-sandbox-") as tmp:
        script = Path(tmp) / "script.py"
        script.write_text(code, encoding="utf-8")

        if USE_DOCKER:
            return _run_docker(str(script), stdin)
        return _run_subprocess(str(script), stdin)


def execute_shell(command: str) -> dict:
    """Execute a shell command (non-Python) in a subprocess with timeout.

    Only use for safe read-only commands (lint, test, format checks).
    Returns: {"success": bool, "stdout": str, "stderr": str, "returncode": int}
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:4000],
            "stderr": result.stderr[:2000],
            "returncode": result.returncode,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Timed out", "returncode": -1, "timed_out": True}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1, "timed_out": False}


def validate_python_syntax(code: str) -> dict:
    """Check Python syntax without executing.

    Returns: {"valid": bool, "error": str | None, "line": int | None}
    """
    try:
        compile(code, "<string>", "exec")
        return {"valid": True, "error": None, "line": None}
    except SyntaxError as e:
        return {"valid": False, "error": str(e.msg), "line": e.lineno}
    except Exception as e:
        return {"valid": False, "error": str(e), "line": None}


# ── Internal helpers ─────────────────────────────────────────────────────────

def _run_subprocess(script_path: str, stdin: str) -> dict:
    """Run a Python script in a subprocess."""
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        log.info("sandbox subprocess: returncode=%d", result.returncode)
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:4000],
            "stderr": result.stderr[:2000],
            "returncode": result.returncode,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        log.warning("sandbox: execution timed out after %ds", TIMEOUT)
        return {"success": False, "stdout": "", "stderr": f"Execution timed out after {TIMEOUT}s", "returncode": -1, "timed_out": True}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1, "timed_out": False}


def _run_docker(script_path: str, stdin: str) -> dict:
    """Run a Python script inside a Docker container (better isolation)."""
    try:
        result = subprocess.run(
            [
                "docker", "run", "--rm",
                "--network=none",         # no internet
                "--memory=256m",
                "--cpus=0.5",
                f"--volume={script_path}:/sandbox/script.py:ro",
                DOCKER_IMAGE,
                "python", "/sandbox/script.py",
            ],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=TIMEOUT + 10,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:4000],
            "stderr": result.stderr[:2000],
            "returncode": result.returncode,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Docker execution timed out", "returncode": -1, "timed_out": True}
    except FileNotFoundError:
        log.warning("Docker not available — falling back to subprocess")
        return _run_subprocess(script_path, stdin)
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1, "timed_out": False}
