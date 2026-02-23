"""PagerDuty tool — incident management and on-call operations.

Used by sre_ops to create, acknowledge, and resolve incidents,
page on-call engineers, and add timeline notes.

Env vars:
  PAGERDUTY_API_KEY    — PagerDuty REST API v2 key (account or user token)
  PAGERDUTY_FROM_EMAIL — Email of the user acting on behalf of (required for some ops)
  PAGERDUTY_SERVICE_ID — Default PagerDuty service ID
"""

import logging
import os

import httpx

log = logging.getLogger(__name__)

API_KEY = os.getenv("PAGERDUTY_API_KEY", "")
FROM_EMAIL = os.getenv("PAGERDUTY_FROM_EMAIL", "")
DEFAULT_SERVICE_ID = os.getenv("PAGERDUTY_SERVICE_ID", "")
API_BASE = "https://api.pagerduty.com"
TIMEOUT = 15


def _headers(include_from: bool = False) -> dict:
    h = {
        "Authorization": f"Token token={API_KEY}",
        "Accept": "application/vnd.pagerduty+json;version=2",
        "Content-Type": "application/json",
    }
    if include_from and FROM_EMAIL:
        h["From"] = FROM_EMAIL
    return h


def _available() -> bool:
    return bool(API_KEY)


def create_incident(
    title: str,
    service_id: str = "",
    body: str = "",
    urgency: str = "high",
    escalation_policy_id: str = "",
) -> dict:
    """Create a PagerDuty incident.

    Args:
      title:                 Incident title / summary
      service_id:            PagerDuty service ID (default: PAGERDUTY_SERVICE_ID)
      body:                  Incident body / details
      urgency:               "high" | "low"
      escalation_policy_id:  Optional escalation policy override

    Returns:
      {"success": bool, "incident_id": str, "incident_url": str, "error": str|None}
    """
    if not _available():
        return {"success": False, "incident_id": "", "incident_url": "",
                "error": "PAGERDUTY_API_KEY not set"}
    svc_id = service_id or DEFAULT_SERVICE_ID
    if not svc_id:
        return {"success": False, "incident_id": "", "incident_url": "",
                "error": "service_id required (or set PAGERDUTY_SERVICE_ID)"}

    payload: dict = {
        "incident": {
            "type": "incident",
            "title": title,
            "service": {"id": svc_id, "type": "service_reference"},
            "urgency": urgency,
        }
    }
    if body:
        payload["incident"]["body"] = {"type": "incident_body", "details": body}
    if escalation_policy_id:
        payload["incident"]["escalation_policy"] = {
            "id": escalation_policy_id, "type": "escalation_policy_reference"
        }

    try:
        resp = httpx.post(
            f"{API_BASE}/incidents",
            headers=_headers(include_from=True),
            json=payload,
            timeout=TIMEOUT,
        )
        if resp.status_code == 201:
            data = resp.json().get("incident", {})
            log.warning("Created PagerDuty incident: %s [%s]", title, data.get("id"))
            return {
                "success": True,
                "incident_id": data.get("id", ""),
                "incident_url": data.get("html_url", ""),
                "error": None,
            }
        return {"success": False, "incident_id": "", "incident_url": "", "error": resp.text[:500]}
    except Exception as e:
        return {"success": False, "incident_id": "", "incident_url": "", "error": str(e)}


def resolve_incident(incident_id: str, resolution_note: str = "") -> dict:
    """Resolve a PagerDuty incident.

    Returns:
      {"success": bool, "error": str|None}
    """
    if not _available():
        return {"success": False, "error": "PAGERDUTY_API_KEY not set"}
    payload = {"incident": {"type": "incident", "status": "resolved"}}
    try:
        resp = httpx.put(
            f"{API_BASE}/incidents/{incident_id}",
            headers=_headers(include_from=True),
            json=payload,
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            if resolution_note:
                add_note(incident_id, resolution_note)
            log.info("Resolved PagerDuty incident: %s", incident_id)
            return {"success": True, "error": None}
        return {"success": False, "error": resp.text[:300]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def acknowledge_incident(incident_id: str) -> dict:
    """Acknowledge a PagerDuty incident.

    Returns:
      {"success": bool, "error": str|None}
    """
    if not _available():
        return {"success": False, "error": "PAGERDUTY_API_KEY not set"}
    payload = {"incident": {"type": "incident", "status": "acknowledged"}}
    try:
        resp = httpx.put(
            f"{API_BASE}/incidents/{incident_id}",
            headers=_headers(include_from=True),
            json=payload,
            timeout=TIMEOUT,
        )
        return {"success": resp.status_code == 200,
                "error": None if resp.status_code == 200 else resp.text[:300]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def add_note(incident_id: str, note: str) -> dict:
    """Add a timeline note to an incident.

    Returns:
      {"success": bool, "note_id": str, "error": str|None}
    """
    if not _available():
        return {"success": False, "note_id": "", "error": "PAGERDUTY_API_KEY not set"}
    payload = {"note": {"content": note}}
    try:
        resp = httpx.post(
            f"{API_BASE}/incidents/{incident_id}/notes",
            headers=_headers(include_from=True),
            json=payload,
            timeout=TIMEOUT,
        )
        if resp.status_code == 201:
            return {"success": True, "note_id": resp.json().get("note", {}).get("id", ""), "error": None}
        return {"success": False, "note_id": "", "error": resp.text[:300]}
    except Exception as e:
        return {"success": False, "note_id": "", "error": str(e)}


def list_incidents(status: str = "triggered,acknowledged", limit: int = 20) -> dict:
    """List active incidents.

    Args:
      status: Comma-separated status filter: triggered, acknowledged, resolved
      limit:  Max incidents to return

    Returns:
      {"success": bool, "incidents": list[{"id","title","status","urgency","created_at"}]}
    """
    if not _available():
        return {"success": False, "incidents": [], "error": "PAGERDUTY_API_KEY not set"}
    params: dict = {"statuses[]": status.split(","), "limit": limit, "sort_by": "created_at:desc"}
    try:
        resp = httpx.get(f"{API_BASE}/incidents", headers=_headers(), params=params, timeout=TIMEOUT)
        if resp.status_code == 200:
            incidents = [
                {
                    "id": i["id"],
                    "title": i["title"],
                    "status": i["status"],
                    "urgency": i["urgency"],
                    "created_at": i.get("created_at", ""),
                    "url": i.get("html_url", ""),
                }
                for i in resp.json().get("incidents", [])
            ]
            return {"success": True, "incidents": incidents, "error": None}
        return {"success": False, "incidents": [], "error": resp.text[:300]}
    except Exception as e:
        return {"success": False, "incidents": [], "error": str(e)}
