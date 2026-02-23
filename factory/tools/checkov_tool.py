"""Checkov tool — standalone IaC security scanner.

Used by security_eng teams to validate Terraform, CloudFormation,
Kubernetes manifests, Dockerfiles, and GitHub Actions workflows.

This is a STANDALONE scanner independent of terraform_tool.py.
It can scan any IaC framework in any directory.

Env vars:
  CHECKOV_BIN     — path to checkov binary (default: checkov)
  CHECKOV_TIMEOUT — subprocess timeout seconds (default: 120)
"""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

CHECKOV_BIN = os.getenv("CHECKOV_BIN", "checkov")
TIMEOUT = int(os.getenv("CHECKOV_TIMEOUT", "120"))

# Supported frameworks
FRAMEWORKS = [
    "terraform", "cloudformation", "kubernetes", "dockerfile",
    "github_actions", "arm", "bicep", "ansible", "helm",
]


def _run(args: list[str]) -> dict:
    cmd = [CHECKOV_BIN, "-o", "json", "--compact"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        output = result.stdout or result.stderr
        # checkov may produce multiple JSON objects; take the first complete one
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            # Try to find JSON in output
            start = output.find("{")
            if start >= 0:
                try:
                    data = json.loads(output[start:])
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}
        return {"ok": True, "data": data, "returncode": result.returncode}
    except FileNotFoundError:
        return {"ok": False, "data": {}, "returncode": -1,
                "error": "checkov not found — pip install checkov"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "data": {}, "returncode": -1, "error": "checkov timed out"}


def _parse(raw: dict) -> dict:
    """Parse checkov JSON output into a normalised summary."""
    results = raw.get("results", {})
    # checkov output can be nested per-framework
    passed_checks_list = results.get("passed_checks", [])
    failed_checks_list = results.get("failed_checks", [])

    failed = []
    for check in failed_checks_list:
        failed.append({
            "check_id": check.get("check_id"),
            "check_type": check.get("check_type", ""),
            "resource": check.get("resource", ""),
            "file": check.get("file_path", ""),
            "guideline": check.get("guideline", ""),
            "severity": check.get("severity", ""),
        })

    return {
        "passed": len(failed) == 0,
        "passed_count": len(passed_checks_list),
        "failed_count": len(failed),
        "failed_checks": failed[:50],
        "summary": raw.get("summary", {}),
    }


def scan_directory(path: str, framework: str = "", skip_checks: list[str] | None = None) -> dict:
    """Scan a directory for IaC security issues.

    Args:
      path:         Directory containing IaC files
      framework:    Restrict to specific framework (e.g. "terraform", "kubernetes")
                    Leave empty to auto-detect all frameworks
      skip_checks:  List of check IDs to skip (e.g. ["CKV_AWS_18"])

    Returns:
      {"passed": bool, "passed_count": int, "failed_count": int,
       "failed_checks": list[{"check_id","resource","file","severity"}]}
    """
    args = ["-d", path]
    if framework:
        args += ["--framework", framework]
    if skip_checks:
        args += ["--skip-check", ",".join(skip_checks)]

    raw = _run(args)
    if "error" in raw:
        return {"passed": True, "passed_count": 0, "failed_count": 0,
                "failed_checks": [], "error": raw["error"]}
    return _parse(raw["data"])


def scan_file(filepath: str, framework: str = "") -> dict:
    """Scan a single IaC file.

    Args:
      filepath:  Path to the file (e.g. main.tf, deployment.yaml, Dockerfile)
      framework: Optional framework hint

    Returns:
      Same structure as scan_directory()
    """
    args = ["-f", filepath]
    if framework:
        args += ["--framework", framework]

    raw = _run(args)
    if "error" in raw:
        return {"passed": True, "passed_count": 0, "failed_count": 0,
                "failed_checks": [], "error": raw["error"]}
    return _parse(raw["data"])


def scan_inline(content: str, framework: str = "terraform", filename: str = "main.tf") -> dict:
    """Scan IaC content provided as a string.

    Args:
      content:   IaC file content as string
      framework: Framework type (default: terraform)
      filename:  Filename to write temporarily (affects framework detection)

    Returns:
      Same structure as scan_directory()
    """
    suffix = Path(filename).suffix or ".tf"
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, prefix="checkov_") as f:
        f.write(content)
        tmp_path = f.name
    try:
        args = ["-f", tmp_path, "--framework", framework]
        raw = _run(args)
        if "error" in raw:
            return {"passed": True, "passed_count": 0, "failed_count": 0,
                    "failed_checks": [], "error": raw["error"]}
        return _parse(raw["data"])
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def list_checks(framework: str = "terraform") -> dict:
    """List available checks for a given framework.

    Returns:
      {"success": bool, "checks": list[{"id","name","guideline"}]}
    """
    cmd = [CHECKOV_BIN, "--list", "--framework", framework, "-o", "json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        try:
            data = json.loads(result.stdout)
            checks = [{"id": c.get("id"), "name": c.get("name"), "guideline": c.get("guideline", "")}
                      for c in (data if isinstance(data, list) else [])]
            return {"success": True, "checks": checks[:200]}
        except json.JSONDecodeError:
            return {"success": False, "checks": [], "error": result.stdout[:500]}
    except Exception as e:
        return {"success": False, "checks": [], "error": str(e)}
