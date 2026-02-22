"""Plane tool — open-source JIRA alternative for project/issue tracking.

Self-hosted: https://plane.so  (MIT license)
Docker compose: https://github.com/makeplane/plane

Env vars:
  PLANE_BASE_URL   — Plane instance URL e.g. http://plane:8080
  PLANE_API_KEY    — Plane API key (Settings → API Tokens)
  PLANE_WORKSPACE  — workspace slug (default: ai-factory)
"""

import logging
import os

import httpx

log = logging.getLogger(__name__)

PLANE_BASE_URL = os.getenv("PLANE_BASE_URL", "http://localhost:8080")
PLANE_API_KEY = os.getenv("PLANE_API_KEY", "")
PLANE_WORKSPACE = os.getenv("PLANE_WORKSPACE", "ai-factory")

API = f"{PLANE_BASE_URL}/api/v1"


def _headers() -> dict:
    return {"X-Api-Key": PLANE_API_KEY, "Content-Type": "application/json"}


def _available() -> bool:
    return bool(PLANE_API_KEY and PLANE_BASE_URL)


# ── Projects ─────────────────────────────────────────────────────────────────

def create_project(name: str, identifier: str, description: str = "") -> dict:
    """Create a Plane project.

    Returns: {"project_id": str, "project_url": str}
    """
    if not _available():
        log.warning("Plane not configured (PLANE_API_KEY missing)")
        return {"project_id": "", "project_url": "", "warning": "Plane not configured"}
    try:
        resp = httpx.post(
            f"{API}/workspaces/{PLANE_WORKSPACE}/projects/",
            headers=_headers(),
            json={"name": name, "identifier": identifier.upper()[:5], "description": description, "network": 0},
            timeout=15,
        )
        resp.raise_for_status()
        d = resp.json()
        pid = d.get("id", "")
        url = f"{PLANE_BASE_URL}/{PLANE_WORKSPACE}/projects/{pid}/issues/"
        log.info("Created Plane project: %s (%s)", name, pid)
        return {"project_id": pid, "project_url": url}
    except Exception as e:
        log.warning("Plane create_project failed: %s", e)
        return {"project_id": "", "project_url": "", "error": str(e)}


def get_or_create_project(name: str, identifier: str) -> str:
    """Return existing project id or create a new one. Returns project_id."""
    try:
        resp = httpx.get(
            f"{API}/workspaces/{PLANE_WORKSPACE}/projects/",
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        for p in resp.json().get("results", []):
            if p.get("name") == name:
                return p["id"]
    except Exception:
        pass
    result = create_project(name, identifier)
    return result.get("project_id", "")


# ── Issues ────────────────────────────────────────────────────────────────────

def create_issue(
    project_id: str,
    title: str,
    description: str = "",
    priority: str = "medium",  # urgent | high | medium | low | none
    labels: list[str] | None = None,
) -> dict:
    """Create a Plane issue (story/task/bug).

    Returns: {"issue_id": str, "issue_url": str, "sequence_id": int}
    """
    if not _available():
        return {"issue_id": "", "issue_url": "", "warning": "Plane not configured"}
    try:
        payload: dict = {
            "name": title,
            "description_html": f"<p>{description}</p>",
            "priority": priority,
            "state": "backlog",
        }
        resp = httpx.post(
            f"{API}/workspaces/{PLANE_WORKSPACE}/projects/{project_id}/issues/",
            headers=_headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        d = resp.json()
        iid = d.get("id", "")
        seq = d.get("sequence_id", 0)
        url = f"{PLANE_BASE_URL}/{PLANE_WORKSPACE}/projects/{project_id}/issues/{iid}/"
        log.info("Created Plane issue #%d: %s", seq, title)
        return {"issue_id": iid, "issue_url": url, "sequence_id": seq}
    except Exception as e:
        log.warning("Plane create_issue failed: %s", e)
        return {"issue_id": "", "issue_url": "", "error": str(e)}


def list_issues(project_id: str, state: str = "") -> dict:
    """List issues for a project.

    Returns: {"issues": [...], "count": int}
    """
    if not _available():
        return {"issues": [], "count": 0, "warning": "Plane not configured"}
    try:
        params = {}
        if state:
            params["state"] = state
        resp = httpx.get(
            f"{API}/workspaces/{PLANE_WORKSPACE}/projects/{project_id}/issues/",
            headers=_headers(),
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        issues = [
            {
                "id": i["id"],
                "title": i.get("name", ""),
                "priority": i.get("priority", ""),
                "state": i.get("state_detail", {}).get("name", ""),
                "url": f"{PLANE_BASE_URL}/{PLANE_WORKSPACE}/projects/{project_id}/issues/{i['id']}/",
            }
            for i in resp.json().get("results", [])
        ]
        return {"issues": issues, "count": len(issues)}
    except Exception as e:
        return {"issues": [], "count": 0, "error": str(e)}


def update_issue_state(project_id: str, issue_id: str, state_name: str) -> dict:
    """Move an issue to a different state (e.g., 'In Progress', 'Done')."""
    if not _available():
        return {"updated": False, "warning": "Plane not configured"}
    try:
        # First, find the state id by name
        resp = httpx.get(
            f"{API}/workspaces/{PLANE_WORKSPACE}/projects/{project_id}/states/",
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        state_id = None
        for s in resp.json().get("results", []):
            if s.get("name", "").lower() == state_name.lower():
                state_id = s["id"]
                break
        if not state_id:
            return {"updated": False, "error": f"State '{state_name}' not found"}

        patch = httpx.patch(
            f"{API}/workspaces/{PLANE_WORKSPACE}/projects/{project_id}/issues/{issue_id}/",
            headers=_headers(),
            json={"state": state_id},
            timeout=10,
        )
        patch.raise_for_status()
        return {"updated": True, "state": state_name}
    except Exception as e:
        return {"updated": False, "error": str(e)}


# ── Cycles (Sprints) ──────────────────────────────────────────────────────────

def create_cycle(project_id: str, name: str, start_date: str, end_date: str) -> dict:
    """Create a sprint/cycle.

    start_date / end_date: 'YYYY-MM-DD'
    Returns: {"cycle_id": str}
    """
    if not _available():
        return {"cycle_id": "", "warning": "Plane not configured"}
    try:
        resp = httpx.post(
            f"{API}/workspaces/{PLANE_WORKSPACE}/projects/{project_id}/cycles/",
            headers=_headers(),
            json={"name": name, "start_date": start_date, "end_date": end_date},
            timeout=15,
        )
        resp.raise_for_status()
        return {"cycle_id": resp.json().get("id", "")}
    except Exception as e:
        return {"cycle_id": "", "error": str(e)}
