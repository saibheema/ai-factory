"""Helm tool — manage Kubernetes applications via Helm charts.

Used by devops and sre_ops for install, upgrade, rollback, and status checks.

Env vars:
  HELM_BIN        — path to helm binary (default: helm)
  HELM_NAMESPACE  — default namespace (default: default)
  HELM_TIMEOUT    — command timeout in seconds (default: 120)
"""

import logging
import os
import subprocess

log = logging.getLogger(__name__)

HELM_BIN = os.getenv("HELM_BIN", "helm")
NAMESPACE = os.getenv("HELM_NAMESPACE", "default")
TIMEOUT = int(os.getenv("HELM_TIMEOUT", "120"))


def _run(args: list[str]) -> dict:
    try:
        result = subprocess.run(
            [HELM_BIN] + args,
            capture_output=True, text=True, timeout=TIMEOUT,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:8000],
            "stderr": result.stderr[:2000],
            "returncode": result.returncode,
        }
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": "helm not found in PATH", "returncode": -1}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "helm command timed out", "returncode": -1}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


def install_chart(
    release_name: str,
    chart: str,
    namespace: str = "",
    values: dict | None = None,
    set_args: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """Install a Helm chart.

    Args:
      release_name: Helm release name
      chart: Chart reference (e.g. bitnami/nginx or ./charts/myapp)
      values: Optional dict of values (written to a temp values.yaml)
      set_args: Optional list of --set key=value strings
      dry_run: If True, runs with --dry-run flag

    Returns:
      {"success": bool, "stdout": str, "stderr": str}
    """
    import tempfile, json
    ns = namespace or NAMESPACE
    args = ["install", release_name, chart, "-n", ns, "--create-namespace"]
    if dry_run:
        args.append("--dry-run")
    if set_args:
        for s in set_args:
            args += ["--set", s]
    if values:
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            import yaml  # type: ignore[import]
            yaml.dump(values, f)
            args += ["-f", f.name]
    return _run(args)


def upgrade_chart(
    release_name: str,
    chart: str,
    namespace: str = "",
    set_args: list[str] | None = None,
    atomic: bool = True,
) -> dict:
    """Upgrade (or install) a Helm release."""
    ns = namespace or NAMESPACE
    args = ["upgrade", "--install", release_name, chart, "-n", ns]
    if atomic:
        args.append("--atomic")
    if set_args:
        for s in set_args:
            args += ["--set", s]
    return _run(args)


def rollback_release(release_name: str, revision: int = 0, namespace: str = "") -> dict:
    """Rollback a release to a previous revision (0 = previous)."""
    ns = namespace or NAMESPACE
    args = ["rollback", release_name, str(revision), "-n", ns]
    return _run(args)


def release_status(release_name: str, namespace: str = "") -> dict:
    """Get the status of a Helm release."""
    ns = namespace or NAMESPACE
    return _run(["status", release_name, "-n", ns])


def list_releases(namespace: str = "") -> dict:
    """List all Helm releases in a namespace."""
    ns = namespace or NAMESPACE
    return _run(["list", "-n", ns, "--output", "json"])


def uninstall_release(release_name: str, namespace: str = "") -> dict:
    """Uninstall a Helm release."""
    ns = namespace or NAMESPACE
    return _run(["uninstall", release_name, "-n", ns])


def lint_chart(chart_path: str) -> dict:
    """Lint a Helm chart for errors and best practices."""
    return _run(["lint", chart_path])


def template_chart(
    release_name: str, chart: str, namespace: str = "", set_args: list[str] | None = None
) -> dict:
    """Render chart templates without installing (useful for review)."""
    ns = namespace or NAMESPACE
    args = ["template", release_name, chart, "-n", ns]
    if set_args:
        for s in set_args:
            args += ["--set", s]
    return _run(args)
