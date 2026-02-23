"""Jira tool — issue and sprint management via Jira REST API v3.

Used by product_mgmt, biz_analysis, and feature_eng teams to
create user stories, link bugs, track sprints, and run JQL queries.

Note: This is a *native Jira* integration distinct from Plane.
     Set JIRA_ENABLED=false if your project uses Plane exclusively.

Env vars:
  JIRA_BASE_URL   — e.g. https://company.atlassian.net
  JIRA_EMAIL      — Atlassian account email
  JIRA_TOKEN      — Atlassian API token
  JIRA_PROJECT    — default project key, e.g. AIF
"""

import base64
import logging
import os

import httpx

log = logging.getLogger(__name__)

BASE_URL = os.getenv("JIRA_BASE_URL", "").rstrip("/")
EMAIL = os.getenv("JIRA_EMAIL", "")
TOKEN = os.getenv("JIRA_TOKEN", "")
PROJECT = os.getenv("JIRA_PROJECT", "AIF")
API = f"{BASE_URL}/rest/api/3"


def _headers() -> dict:
    creds = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _available() -> bool:
    return bool(BASE_URL and EMAIL and TOKEN)


def create_issue(
    summary: str,
    description: str = "",
    issue_type: str = "Story",
    priority: str = "Medium",
    project_key: str = "",
    labels: list[str] | None = None,
    assignee_account_id: str = "",
) -> dict:
    """Create a Jira issue.

    Args:
      summary:            Issue title
      description:        ADF-format description (plain text auto-converted)
      issue_type:         Story | Bug | Task | Epic | Sub-task
      priority:           Highest | High | Medium | Low | Lowest
      project_key:        Jira project key (default: JIRA_PROJECT)
      labels:             Optional list of label strings
      assignee_account_id: Atlassian account ID for assignee

    Returns:
      {"success": bool, "key": str, "issue_url": str, "error": str|None}
    """
    if not _available():
        return {"success": False, "key": "", "issue_url": "",
                "error": "Jira credentials not configured"}

    # Convert plain text to Atlassian Document Format (ADF)
    adf_body = {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
    } if description else None

    fields: dict = {
        "project": {"key": project_key or PROJECT},
        "summary": summary,
        "issuetype": {"name": issue_type},
        "priority": {"name": priority},
    }
    if adf_body:
        fields["description"] = adf_body
    if labels:
        fields["labels"] = labels
    if assignee_account_id:
        fields["assignee"] = {"accountId": assignee_account_id}

    try:
        resp = httpx.post(f"{API}/issue", headers=_headers(), json={"fields": fields}, timeout=20)
        if resp.status_code == 201:
            data = resp.json()
            key = data.get("key", "")
            url = f"{BASE_URL}/browse/{key}"
            log.info("Created Jira issue: %s", key)
            return {"success": True, "key": key, "issue_url": url, "error": None}
        return {"success": False, "key": "", "issue_url": "", "error": resp.text[:500]}
    except Exception as e:
        return {"success": False, "key": "", "issue_url": "", "error": str(e)}


def get_issue(key: str) -> dict:
    """Fetch a Jira issue by key.

    Returns:
      {"success": bool, "key": str, "summary": str, "status": str, "assignee": str, "priority": str}
    """
    if not _available():
        return {"success": False, "key": key, "summary": "", "status": "", "assignee": "", "priority": ""}
    try:
        resp = httpx.get(f"{API}/issue/{key}", headers=_headers(), timeout=10)
        if resp.status_code == 200:
            d = resp.json().get("fields", {})
            return {
                "success": True,
                "key": key,
                "summary": d.get("summary", ""),
                "status": d.get("status", {}).get("name", ""),
                "assignee": (d.get("assignee") or {}).get("displayName", ""),
                "priority": d.get("priority", {}).get("name", ""),
                "issue_url": f"{BASE_URL}/browse/{key}",
            }
        return {"success": False, "key": key, "summary": "", "status": "", "assignee": "", "priority": "", "error": resp.text[:200]}
    except Exception as e:
        return {"success": False, "key": key, "error": str(e)}


def search_issues(jql: str, max_results: int = 50) -> dict:
    """Run a JQL search.

    Args:
      jql:         JQL query string, e.g. "project=AIF AND status='In Progress'"
      max_results: Max issues to return (default 50)

    Returns:
      {"success": bool, "total": int, "issues": [{"key": str, "summary": str, "status": str}]}
    """
    if not _available():
        return {"success": False, "total": 0, "issues": [], "error": "Jira credentials not configured"}
    try:
        resp = httpx.post(
            f"{API}/search",
            headers=_headers(),
            json={"jql": jql, "maxResults": max_results, "fields": ["summary", "status", "priority", "assignee"]},
            timeout=15,
        )
        if resp.status_code == 200:
            body = resp.json()
            issues = [
                {
                    "key": i["key"],
                    "summary": i["fields"]["summary"],
                    "status": i["fields"].get("status", {}).get("name", ""),
                    "priority": i["fields"].get("priority", {}).get("name", ""),
                }
                for i in body.get("issues", [])
            ]
            return {"success": True, "total": body.get("total", len(issues)), "issues": issues}
        return {"success": False, "total": 0, "issues": [], "error": resp.text[:500]}
    except Exception as e:
        return {"success": False, "total": 0, "issues": [], "error": str(e)}


def transition_issue(key: str, transition_name: str) -> dict:
    """Move an issue to a new status.

    Common transition_name values: "In Progress", "Done", "In Review", "Backlog"

    Returns:
      {"success": bool, "error": str|None}
    """
    if not _available():
        return {"success": False, "error": "Jira credentials not configured"}
    try:
        # Get available transitions
        t_resp = httpx.get(f"{API}/issue/{key}/transitions", headers=_headers(), timeout=10)
        if t_resp.status_code != 200:
            return {"success": False, "error": t_resp.text[:300]}
        transitions = t_resp.json().get("transitions", [])
        match = next((t for t in transitions if t["name"].lower() == transition_name.lower()), None)
        if not match:
            names = [t["name"] for t in transitions]
            return {"success": False, "error": f"Transition '{transition_name}' not found. Available: {names}"}
        resp = httpx.post(
            f"{API}/issue/{key}/transitions",
            headers=_headers(),
            json={"transition": {"id": match["id"]}},
            timeout=10,
        )
        if resp.status_code == 204:
            log.info("Transitioned %s → %s", key, transition_name)
            return {"success": True, "error": None}
        return {"success": False, "error": resp.text[:300]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def add_comment(key: str, comment: str) -> dict:
    """Add a comment to a Jira issue.

    Returns:
      {"success": bool, "comment_id": str, "error": str|None}
    """
    if not _available():
        return {"success": False, "comment_id": "", "error": "Jira credentials not configured"}
    adf = {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment}]}],
    }
    try:
        resp = httpx.post(
            f"{API}/issue/{key}/comment",
            headers=_headers(),
            json={"body": adf},
            timeout=10,
        )
        if resp.status_code == 201:
            return {"success": True, "comment_id": resp.json().get("id", ""), "error": None}
        return {"success": False, "comment_id": "", "error": resp.text[:300]}
    except Exception as e:
        return {"success": False, "comment_id": "", "error": str(e)}
