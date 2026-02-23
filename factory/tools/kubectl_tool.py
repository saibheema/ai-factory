"""kubectl tool — run kubectl commands for Kubernetes cluster management.

Used by devops and sre_ops teams to inspect, deploy, and manage workloads.

Env vars:
  KUBECTL_BIN       — path to kubectl binary (default: kubectl)
  KUBECTL_NAMESPACE — default namespace (default: default)
  KUBECTL_TIMEOUT   — command timeout in seconds (default: 30)
  KUBECONFIG        — path to kubeconfig file (optional)
"""

import logging
import os
import subprocess

log = logging.getLogger(__name__)

KUBECTL_BIN = os.getenv("KUBECTL_BIN", "kubectl")
NAMESPACE = os.getenv("KUBECTL_NAMESPACE", "default")
TIMEOUT = int(os.getenv("KUBECTL_TIMEOUT", "30"))


def _run(args: list[str]) -> dict:
    env = os.environ.copy()
    try:
        result = subprocess.run(
            [KUBECTL_BIN] + args,
            capture_output=True, text=True, timeout=TIMEOUT, env=env,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:8000],
            "stderr": result.stderr[:2000],
            "returncode": result.returncode,
        }
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": "kubectl not found in PATH", "returncode": -1}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "kubectl timed out", "returncode": -1}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


def get_pods(namespace: str = "") -> dict:
    """List pods in a namespace.

    Returns:
      {"success": bool, "stdout": str, "pods": list[dict]}
    """
    ns = namespace or NAMESPACE
    result = _run(["get", "pods", "-n", ns, "-o", "wide"])
    return result


def get_deployments(namespace: str = "") -> dict:
    """List deployments in a namespace."""
    ns = namespace or NAMESPACE
    return _run(["get", "deployments", "-n", ns, "-o", "wide"])


def describe_resource(resource: str, name: str, namespace: str = "") -> dict:
    """Describe a Kubernetes resource (pod, deployment, service, etc.)."""
    ns = namespace or NAMESPACE
    return _run(["describe", resource, name, "-n", ns])


def get_logs(pod_name: str, namespace: str = "", container: str = "", tail: int = 100) -> dict:
    """Fetch logs from a pod.

    Returns:
      {"success": bool, "stdout": str (log lines), "stderr": str}
    """
    ns = namespace or NAMESPACE
    args = ["logs", pod_name, "-n", ns, f"--tail={tail}"]
    if container:
        args += ["-c", container]
    return _run(args)


def apply_manifest(manifest_yaml: str) -> dict:
    """Apply a Kubernetes manifest YAML string.

    Writes to a temp file and runs kubectl apply -f.

    Returns:
      {"success": bool, "stdout": str, "stderr": str}
    """
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        f.write(manifest_yaml)
        tmp_path = f.name
    try:
        result = _run(["apply", "-f", tmp_path])
    finally:
        os.unlink(tmp_path)
    return result


def rollout_status(deployment: str, namespace: str = "") -> dict:
    """Check rollout status of a deployment."""
    ns = namespace or NAMESPACE
    return _run(["rollout", "status", f"deployment/{deployment}", "-n", ns, "--timeout=60s"])


def rollout_restart(deployment: str, namespace: str = "") -> dict:
    """Restart a deployment (rolling restart)."""
    ns = namespace or NAMESPACE
    return _run(["rollout", "restart", f"deployment/{deployment}", "-n", ns])


def get_events(namespace: str = "") -> dict:
    """Get recent cluster events, sorted by timestamp."""
    ns = namespace or NAMESPACE
    return _run(["get", "events", "-n", ns, "--sort-by=.lastTimestamp"])


def scale_deployment(deployment: str, replicas: int, namespace: str = "") -> dict:
    """Scale a deployment to the specified replica count."""
    ns = namespace or NAMESPACE
    return _run(["scale", f"deployment/{deployment}", f"--replicas={replicas}", "-n", ns])
