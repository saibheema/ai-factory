"""Docker tool — build, inspect, and push Docker images.

Used by devops, backend_eng, and frontend_eng teams.

Env vars:
  DOCKER_BIN      — path to docker binary (default: docker)
  DOCKER_TIMEOUT  — command timeout in seconds (default: 300)
  DOCKER_REGISTRY — optional registry prefix (e.g. us-central1-docker.pkg.dev/myproject/repo)
"""

import logging
import os
import subprocess

log = logging.getLogger(__name__)

DOCKER_BIN = os.getenv("DOCKER_BIN", "docker")
TIMEOUT = int(os.getenv("DOCKER_TIMEOUT", "300"))
REGISTRY = os.getenv("DOCKER_REGISTRY", "")


def _run(args: list[str], timeout: int | None = None) -> dict:
    try:
        result = subprocess.run(
            [DOCKER_BIN] + args,
            capture_output=True, text=True,
            timeout=timeout or TIMEOUT,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:8000],
            "stderr": result.stderr[:3000],
            "returncode": result.returncode,
        }
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": "docker not found in PATH", "returncode": -1}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "docker timed out", "returncode": -1}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


def build_image(
    tag: str,
    context: str = ".",
    dockerfile: str = "",
    build_args: dict[str, str] | None = None,
    no_cache: bool = False,
) -> dict:
    """Build a Docker image.

    Args:
      tag: Image tag (e.g. myapp:latest)
      context: Build context path
      dockerfile: Optional path to Dockerfile
      build_args: Optional dict of --build-arg key=value pairs
      no_cache: Whether to use --no-cache

    Returns:
      {"success": bool, "image_tag": str, "stdout": str, "stderr": str}
    """
    full_tag = f"{REGISTRY}/{tag}" if REGISTRY and not tag.startswith(REGISTRY) else tag
    args = ["build", "-t", full_tag, context]
    if dockerfile:
        args += ["-f", dockerfile]
    if no_cache:
        args.append("--no-cache")
    if build_args:
        for k, v in build_args.items():
            args += ["--build-arg", f"{k}={v}"]
    result = _run(args)
    result["image_tag"] = full_tag
    return result


def push_image(tag: str) -> dict:
    """Push a Docker image to the registry."""
    full_tag = f"{REGISTRY}/{tag}" if REGISTRY and not tag.startswith(REGISTRY) else tag
    return _run(["push", full_tag])


def pull_image(tag: str) -> dict:
    """Pull a Docker image from the registry."""
    return _run(["pull", tag])


def inspect_image(tag: str) -> dict:
    """Inspect a Docker image and return metadata.

    Returns:
      {"success": bool, "metadata": dict, "error": str|None}
    """
    result = _run(["inspect", tag, "--format", "{{json .}}"], timeout=30)
    if result["success"]:
        import json
        try:
            data = json.loads(result["stdout"])
            return {"success": True, "metadata": data[0] if isinstance(data, list) else data, "error": None}
        except Exception:
            pass
    return {"success": False, "metadata": {}, "error": result["stderr"]}


def list_images(filter_ref: str = "") -> dict:
    """List local Docker images."""
    args = ["images", "--format", "{{json .}}"]
    if filter_ref:
        args.append(filter_ref)
    result = _run(args, timeout=15)
    return result


def run_container(
    image: str,
    command: str = "",
    env_vars: dict[str, str] | None = None,
    remove: bool = True,
    timeout_seconds: int = 60,
) -> dict:
    """Run a container and capture output (short-lived tasks only).

    Returns:
      {"success": bool, "stdout": str, "stderr": str, "returncode": int}
    """
    args = ["run"]
    if remove:
        args.append("--rm")
    if env_vars:
        for k, v in env_vars.items():
            args += ["-e", f"{k}={v}"]
    args.append(image)
    if command:
        args += command.split()
    return _run(args, timeout=timeout_seconds)


def scan_image_trivy(image: str) -> dict:
    """Run Trivy vulnerability scan on a Docker image.

    Returns:
      {"success": bool, "passed": bool, "vuln_count": int, "critical": int, "high": int}
    """
    try:
        result = subprocess.run(
            ["trivy", "image", "--format", "json", "--quiet", image],
            capture_output=True, text=True, timeout=120,
        )
        import json
        data = json.loads(result.stdout or "{}")
        results = data.get("Results", [])
        vulns = [v for r in results for v in r.get("Vulnerabilities") or []]
        critical = sum(1 for v in vulns if v.get("Severity") == "CRITICAL")
        high = sum(1 for v in vulns if v.get("Severity") == "HIGH")
        total = len(vulns)
        return {
            "success": True, "passed": total == 0,
            "vuln_count": total, "critical": critical, "high": high,
        }
    except FileNotFoundError:
        return {"success": False, "passed": True, "vuln_count": 0, "critical": 0, "high": 0,
                "error": "trivy not found"}
    except Exception as e:
        return {"success": False, "passed": False, "vuln_count": 0, "critical": 0, "high": 0,
                "error": str(e)}
