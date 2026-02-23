"""Cloud Run tool — deploy and manage Google Cloud Run services.

Used by devops and sre_ops teams to deploy microservices,
check service health, manage revisions, and set traffic splits.

Env vars:
  GCP_PROJECT   — GCP project ID (default: unicon-494419)
  GCP_REGION    — default Cloud Run region (default: us-central1)
  GCLOUD_BIN    — path to gcloud CLI binary (default: gcloud)
  CLOUDRUN_TIMEOUT — gcloud command timeout seconds (default: 300)
"""

import json
import logging
import os
import subprocess

log = logging.getLogger(__name__)

PROJECT = os.getenv("GCP_PROJECT", "unicon-494419")
REGION = os.getenv("GCP_REGION", "us-central1")
GCLOUD = os.getenv("GCLOUD_BIN", "gcloud")
TIMEOUT = int(os.getenv("CLOUDRUN_TIMEOUT", "300"))


def _run(args: list[str], json_output: bool = True) -> dict:
    cmd = [GCLOUD] + args + ["--project", PROJECT]
    if json_output:
        cmd += ["--format", "json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        if json_output and result.stdout.strip():
            try:
                return {"ok": result.returncode == 0, "data": json.loads(result.stdout),
                        "stderr": result.stderr[:500]}
            except json.JSONDecodeError:
                pass
        return {"ok": result.returncode == 0, "data": result.stdout[:2000],
                "stderr": result.stderr[:500]}
    except FileNotFoundError:
        return {"ok": False, "data": None, "stderr": "gcloud not found — install Google Cloud SDK"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "data": None, "stderr": f"gcloud timed out after {TIMEOUT}s"}


def deploy_service(
    service: str,
    image: str,
    region: str = "",
    env_vars: dict | None = None,
    memory: str = "512Mi",
    cpu: str = "1",
    min_instances: int = 0,
    max_instances: int = 10,
    allow_unauthenticated: bool = False,
) -> dict:
    """Deploy a container image to Cloud Run.

    Args:
      service:                Service name
      image:                  Full container image URI (e.g. gcr.io/project/img:tag)
      region:                 Cloud Run region (default: GCP_REGION)
      env_vars:               Dict of environment variables
      memory:                 Memory limit (default: 512Mi)
      cpu:                    CPU count (default: 1)
      min_instances:          Min instances for scale-to-zero (default: 0)
      max_instances:          Max instances (default: 10)
      allow_unauthenticated:  Allow public access (default: False)

    Returns:
      {"success": bool, "service_url": str, "error": str|None}
    """
    args = [
        "run", "deploy", service,
        "--image", image,
        "--region", region or REGION,
        "--memory", memory,
        "--cpu", cpu,
        f"--min-instances={min_instances}",
        f"--max-instances={max_instances}",
    ]
    if env_vars:
        env_str = ",".join(f"{k}={v}" for k, v in env_vars.items())
        args += ["--set-env-vars", env_str]
    if allow_unauthenticated:
        args.append("--allow-unauthenticated")

    log.info("Deploying Cloud Run service: %s from %s", service, image)
    result = _run(args)
    if result["ok"]:
        data = result["data"]
        if isinstance(data, dict):
            url = data.get("status", {}).get("url", "") or data.get("url", "")
        else:
            # Extract URL from text output
            import re
            match = re.search(r"https://\S+\.run\.app", result.get("stderr", ""))
            url = match.group(0) if match else ""
        return {"success": True, "service_url": url, "error": None}
    return {"success": False, "service_url": "", "error": result["stderr"]}


def describe_service(service: str, region: str = "") -> dict:
    """Get details of a Cloud Run service.

    Returns:
      {"success": bool, "url": str, "image": str, "traffic": list,
       "last_modified": str, "error": str|None}
    """
    result = _run(["run", "services", "describe", service, "--region", region or REGION])
    if not result["ok"]:
        return {"success": False, "url": "", "image": "", "traffic": [], "error": result["stderr"]}
    data = result["data"] or {}
    spec = data.get("spec", {}).get("template", {}).get("spec", {})
    containers = spec.get("containers", [{}])
    image = containers[0].get("image", "") if containers else ""
    traffic = data.get("spec", {}).get("traffic", [])
    return {
        "success": True,
        "url": data.get("status", {}).get("url", ""),
        "image": image,
        "traffic": traffic,
        "last_modified": data.get("metadata", {}).get("annotations", {}).get(
            "serving.knative.dev/lastModifier", ""),
        "error": None,
    }


def list_services(region: str = "") -> dict:
    """List all Cloud Run services in a region.

    Returns:
      {"success": bool, "services": list[{"name": str, "url": str, "region": str}]}
    """
    result = _run(["run", "services", "list", "--region", region or REGION])
    if not result["ok"]:
        return {"success": False, "services": [], "error": result["stderr"]}
    data = result["data"] or []
    services = [
        {
            "name": svc.get("metadata", {}).get("name", ""),
            "url": svc.get("status", {}).get("url", ""),
            "region": region or REGION,
        }
        for svc in (data if isinstance(data, list) else [])
    ]
    return {"success": True, "services": services, "error": None}


def get_service_logs(service: str, region: str = "", limit: int = 50) -> dict:
    """Retrieve recent Cloud Run service logs.

    Returns:
      {"success": bool, "logs": list[str], "error": str|None}
    """
    filter_str = (
        f'resource.type="cloud_run_revision" '
        f'resource.labels.service_name="{service}" '
        f'resource.labels.location="{region or REGION}"'
    )
    result = _run([
        "logging", "read", filter_str,
        "--limit", str(limit),
        "--order", "desc",
    ])
    if not result["ok"]:
        return {"success": False, "logs": [], "error": result["stderr"]}
    entries = result["data"] if isinstance(result["data"], list) else []
    logs = [e.get("textPayload") or str(e.get("jsonPayload", "")) for e in entries]
    return {"success": True, "logs": logs, "error": None}


def set_traffic(service: str, revision_tags: dict, region: str = "") -> dict:
    """Split traffic between Cloud Run revisions.

    Args:
      service:       Service name
      revision_tags: Dict mapping revision names to traffic % e.g.
                     {"LATEST": 80, "my-service-00001-abc": 20}
      region:        Cloud Run region

    Returns:
      {"success": bool, "error": str|None}
    """
    traffic_args = ",".join(f"{rev}={pct}" for rev, pct in revision_tags.items())
    result = _run(["run", "services", "update-traffic", service,
                   "--to-revisions", traffic_args,
                   "--region", region or REGION])
    return {"success": result["ok"], "error": None if result["ok"] else result["stderr"]}
