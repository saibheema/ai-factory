"""GitHub tool — repo management, PRs, issues via GitHub REST API.

Env vars:
  GITHUB_TOKEN  — personal access token or GitHub App token
  GITHUB_ORG    — org/user to create repos under (default: saibheema)
"""

import logging
import os

import httpx

log = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_ORG = os.getenv("GITHUB_ORG", "saibheema")
GITHUB_API = "https://api.github.com"


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


# ── Repo ────────────────────────────────────────────────────────────────────

def create_repo(name: str, description: str = "", private: bool = False) -> dict:
    """Create a GitHub repository under GITHUB_ORG.

    Returns: {"repo_url": str, "clone_url": str, "full_name": str}
    """
    if not GITHUB_TOKEN:
        return {"error": "GITHUB_TOKEN not set", "repo_url": "", "clone_url": ""}
    try:
        resp = httpx.post(
            f"{GITHUB_API}/user/repos",
            headers=_headers(),
            json={"name": name, "description": description, "private": private, "auto_init": True},
            timeout=20,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            log.info("Created repo: %s", data["full_name"])
            return {"repo_url": data["html_url"], "clone_url": data["clone_url"], "full_name": data["full_name"]}
        # Repo already exists — return existing
        if resp.status_code == 422:
            existing = httpx.get(f"{GITHUB_API}/repos/{GITHUB_ORG}/{name}", headers=_headers(), timeout=10).json()
            return {"repo_url": existing["html_url"], "clone_url": existing["clone_url"], "full_name": existing["full_name"]}
        return {"error": resp.text, "repo_url": ""}
    except Exception as e:
        log.warning("create_repo failed: %s", e)
        return {"error": str(e), "repo_url": ""}


def get_repo(full_name: str) -> dict:
    """Fetch metadata for an existing repo."""
    try:
        resp = httpx.get(f"{GITHUB_API}/repos/{full_name}", headers=_headers(), timeout=10)
        resp.raise_for_status()
        d = resp.json()
        return {"repo_url": d["html_url"], "clone_url": d["clone_url"], "default_branch": d["default_branch"]}
    except Exception as e:
        return {"error": str(e)}


# ── Issues ───────────────────────────────────────────────────────────────────

def create_issue(repo_full_name: str, title: str, body: str, labels: list[str] | None = None) -> dict:
    """Create a GitHub issue.

    Returns: {"issue_url": str, "issue_number": int}
    """
    if not GITHUB_TOKEN:
        return {"error": "GITHUB_TOKEN not set", "issue_url": ""}
    try:
        payload: dict = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        resp = httpx.post(
            f"{GITHUB_API}/repos/{repo_full_name}/issues",
            headers=_headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        d = resp.json()
        log.info("Created issue #%d: %s", d["number"], title)
        return {"issue_url": d["html_url"], "issue_number": d["number"]}
    except Exception as e:
        log.warning("create_issue failed: %s", e)
        return {"error": str(e), "issue_url": ""}


def list_issues(repo_full_name: str, state: str = "open") -> dict:
    """List open/closed issues for a repo."""
    try:
        resp = httpx.get(
            f"{GITHUB_API}/repos/{repo_full_name}/issues",
            headers=_headers(),
            params={"state": state, "per_page": 20},
            timeout=15,
        )
        resp.raise_for_status()
        issues = [{"number": i["number"], "title": i["title"], "url": i["html_url"], "state": i["state"]} for i in resp.json()]
        return {"issues": issues, "count": len(issues)}
    except Exception as e:
        return {"error": str(e), "issues": []}


# ── Pull Requests ─────────────────────────────────────────────────────────────

def create_pull_request(
    repo_full_name: str,
    title: str,
    body: str,
    head_branch: str,
    base_branch: str = "main",
) -> dict:
    """Create a pull request.

    Returns: {"pr_url": str, "pr_number": int}
    """
    if not GITHUB_TOKEN:
        return {"error": "GITHUB_TOKEN not set", "pr_url": ""}
    try:
        resp = httpx.post(
            f"{GITHUB_API}/repos/{repo_full_name}/pulls",
            headers=_headers(),
            json={"title": title, "body": body, "head": head_branch, "base": base_branch},
            timeout=15,
        )
        resp.raise_for_status()
        d = resp.json()
        log.info("Created PR #%d: %s", d["number"], title)
        return {"pr_url": d["html_url"], "pr_number": d["number"]}
    except Exception as e:
        log.warning("create_pr failed: %s", e)
        return {"error": str(e), "pr_url": ""}


def list_pull_requests(repo_full_name: str, state: str = "open") -> dict:
    """List PRs for a repo."""
    try:
        resp = httpx.get(
            f"{GITHUB_API}/repos/{repo_full_name}/pulls",
            headers=_headers(),
            params={"state": state, "per_page": 20},
            timeout=15,
        )
        resp.raise_for_status()
        prs = [{"number": p["number"], "title": p["title"], "url": p["html_url"], "state": p["state"]} for p in resp.json()]
        return {"pull_requests": prs, "count": len(prs)}
    except Exception as e:
        return {"error": str(e), "pull_requests": []}


# ── Labels ────────────────────────────────────────────────────────────────────

def ensure_labels(repo_full_name: str, labels: list[dict]) -> dict:
    """Create labels if they don't exist. labels = [{"name": str, "color": str, "description": str}]"""
    if not GITHUB_TOKEN:
        return {"skipped": True}
    created = []
    for lbl in labels:
        try:
            httpx.post(
                f"{GITHUB_API}/repos/{repo_full_name}/labels",
                headers=_headers(),
                json=lbl,
                timeout=10,
            )
            created.append(lbl["name"])
        except Exception:
            pass
    return {"labels_created": created}
