"""Confluence tool — create and update Confluence wiki pages.

Used by docs_team, solution_arch, and compliance teams for
structured documentation, ADR publishing, and audit records.

Env vars:
  CONFLUENCE_URL       — base URL e.g. https://company.atlassian.net/wiki
  CONFLUENCE_TOKEN     — API token (Atlassian personal access token)
  CONFLUENCE_USER      — username/email
  CONFLUENCE_SPACE_KEY — default space key (default: AIF)
"""

import logging
import os

import httpx

log = logging.getLogger(__name__)

BASE_URL = os.getenv("CONFLUENCE_URL", "").rstrip("/")
TOKEN = os.getenv("CONFLUENCE_TOKEN", "")
USER = os.getenv("CONFLUENCE_USER", "")
SPACE_KEY = os.getenv("CONFLUENCE_SPACE_KEY", "AIF")
API_V2 = f"{BASE_URL}/rest/api"


def _headers() -> dict:
    import base64
    creds = base64.b64encode(f"{USER}:{TOKEN}".encode()).decode()
    return {
        "Authorization": f"Basic {creds}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _available() -> bool:
    return bool(BASE_URL and TOKEN and USER)


def create_page(
    title: str,
    body_html: str,
    space_key: str = "",
    parent_id: str = "",
) -> dict:
    """Create a new Confluence page.

    Args:
      title:     Page title
      body_html: Page content as Confluence Storage Format HTML
      space_key: Target space (default: CONFLUENCE_SPACE_KEY)
      parent_id: Optional parent page ID for nesting

    Returns:
      {"success": bool, "page_id": str, "page_url": str, "error": str|None}
    """
    if not _available():
        return {"success": False, "page_id": "", "page_url": "",
                "error": "Confluence credentials not configured"}
    payload: dict = {
        "type": "page",
        "title": title,
        "space": {"key": space_key or SPACE_KEY},
        "body": {"storage": {"value": body_html, "representation": "storage"}},
    }
    if parent_id:
        payload["ancestors"] = [{"id": parent_id}]
    try:
        resp = httpx.post(f"{API_V2}/content", headers=_headers(), json=payload, timeout=20)
        if resp.status_code in (200, 201):
            data = resp.json()
            page_id = data.get("id", "")
            links = data.get("_links", {})
            url = f"{BASE_URL}{links.get('webui', '')}"
            log.info("Created Confluence page: %s (%s)", title, page_id)
            return {"success": True, "page_id": page_id, "page_url": url, "error": None}
        return {"success": False, "page_id": "", "page_url": "", "error": resp.text[:500]}
    except Exception as e:
        log.warning("Confluence create_page failed: %s", e)
        return {"success": False, "page_id": "", "page_url": "", "error": str(e)}


def update_page(page_id: str, title: str, body_html: str, version_number: int = 1) -> dict:
    """Update an existing Confluence page.

    Returns:
      {"success": bool, "page_url": str, "error": str|None}
    """
    if not _available():
        return {"success": False, "page_url": "", "error": "Confluence credentials not configured"}
    payload = {
        "version": {"number": version_number},
        "title": title,
        "type": "page",
        "body": {"storage": {"value": body_html, "representation": "storage"}},
    }
    try:
        resp = httpx.put(f"{API_V2}/content/{page_id}", headers=_headers(), json=payload, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            url = f"{BASE_URL}{data.get('_links', {}).get('webui', '')}"
            return {"success": True, "page_url": url, "error": None}
        return {"success": False, "page_url": "", "error": resp.text[:500]}
    except Exception as e:
        return {"success": False, "page_url": "", "error": str(e)}


def get_page_by_title(title: str, space_key: str = "") -> dict:
    """Find a page by title in a space.

    Returns:
      {"found": bool, "page_id": str, "page_url": str, "version": int}
    """
    if not _available():
        return {"found": False, "page_id": "", "page_url": "", "version": 0}
    params = {"title": title, "spaceKey": space_key or SPACE_KEY, "expand": "version"}
    try:
        resp = httpx.get(f"{API_V2}/content", headers=_headers(), params=params, timeout=10)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                page = results[0]
                url = f"{BASE_URL}{page.get('_links', {}).get('webui', '')}"
                return {
                    "found": True,
                    "page_id": page["id"],
                    "page_url": url,
                    "version": page.get("version", {}).get("number", 1),
                }
        return {"found": False, "page_id": "", "page_url": "", "version": 0}
    except Exception as e:
        return {"found": False, "page_id": "", "page_url": "", "version": 0, "error": str(e)}


def upsert_page(title: str, body_html: str, space_key: str = "", parent_id: str = "") -> dict:
    """Create a page if it doesn't exist, update it if it does.

    Returns:
      {"success": bool, "page_id": str, "page_url": str, "action": "created"|"updated"}
    """
    existing = get_page_by_title(title, space_key)
    if existing["found"]:
        result = update_page(
            existing["page_id"], title, body_html,
            version_number=existing["version"] + 1,
        )
        return {**result, "page_id": existing["page_id"], "action": "updated"}
    result = create_page(title, body_html, space_key, parent_id)
    return {**result, "action": "created"}


def markdown_to_storage(markdown: str) -> str:
    """Very basic Markdown → Confluence Storage Format conversion.

    For full fidelity, integrate the Confluence markdown macro or use pypandoc.
    """
    import re
    html = markdown
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)
    html = re.sub(r"`(.+?)`", r"<code>\1</code>", html)
    # Code blocks
    html = re.sub(
        r"```(\w+)?\n([\s\S]+?)```",
        lambda m: f'<ac:structured-macro ac:name="code"><ac:plain-text-body><![CDATA[{m.group(2)}]]></ac:plain-text-body></ac:structured-macro>',
        html,
    )
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = re.sub(r"(<li>.*</li>)", r"<ul>\1</ul>", html, flags=re.DOTALL)
    html = re.sub(r"\n\n", "<br/>", html)
    return html
