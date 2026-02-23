"""Wikipedia tool — search and retrieve article summaries.

Used by product_mgmt, biz_analysis, solution_arch, and docs_team
to research concepts, technologies, and background information.

Env vars:
  WIKIPEDIA_LANG     — language code (default: en)
  WIKIPEDIA_TIMEOUT  — HTTP timeout seconds (default: 10)
"""

import logging
import os
from urllib.parse import quote_plus

import httpx

log = logging.getLogger(__name__)

LANG = os.getenv("WIKIPEDIA_LANG", "en")
TIMEOUT = int(os.getenv("WIKIPEDIA_TIMEOUT", "10"))
BASE_API = f"https://{LANG}.wikipedia.org/api/rest_v1"
SEARCH_API = f"https://{LANG}.wikipedia.org/w/api.php"


def search(query: str, max_results: int = 5) -> dict:
    """Search Wikipedia for pages matching a query.

    Args:
      query:       Search terms
      max_results: Max results to return (default 5)

    Returns:
      {"results": list[{"title": str, "description": str, "url": str}], "error": str|None}
    """
    try:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": max_results,
            "format": "json",
            "srprop": "snippet",
        }
        resp = httpx.get(SEARCH_API, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        hits = resp.json().get("query", {}).get("search", [])
        results = []
        for h in hits:
            title = h["title"]
            # Strip HTML from snippet
            import re
            snippet = re.sub(r"<[^>]+>", "", h.get("snippet", ""))
            results.append({
                "title": title,
                "description": snippet,
                "url": f"https://{LANG}.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}",
            })
        return {"results": results, "error": None}
    except Exception as e:
        return {"results": [], "error": str(e)}


def get_summary(title: str) -> dict:
    """Get the introduction summary of a Wikipedia article.

    Args:
      title: Article title (exact or near-exact)

    Returns:
      {"found": bool, "title": str, "summary": str, "url": str, "image_url": str|None}
    """
    try:
        encoded = quote_plus(title.replace(" ", "_"))
        resp = httpx.get(f"{BASE_API}/page/summary/{encoded}", timeout=TIMEOUT)
        if resp.status_code == 404:
            # Try search fallback
            search_result = search(title, max_results=1)
            if search_result["results"]:
                return get_summary(search_result["results"][0]["title"])
            return {"found": False, "title": title, "summary": "", "url": "", "image_url": None}
        resp.raise_for_status()
        data = resp.json()
        return {
            "found": True,
            "title": data.get("title", title),
            "summary": data.get("extract", "")[:2000],
            "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
            "image_url": data.get("thumbnail", {}).get("source") if data.get("thumbnail") else None,
        }
    except Exception as e:
        return {"found": False, "title": title, "summary": "", "url": "", "image_url": None, "error": str(e)}


def get_sections(title: str) -> dict:
    """Get the section headings and intro text of a Wikipedia article.

    Returns:
      {"found": bool, "title": str, "sections": list[{"title": str, "text": str}]}
    """
    try:
        params = {
            "action": "parse",
            "page": title,
            "prop": "sections",
            "format": "json",
        }
        resp = httpx.get(SEARCH_API, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            return {"found": False, "title": title, "sections": []}
        sections = [
            {"title": s["line"], "number": s["number"]}
            for s in data.get("parse", {}).get("sections", [])
        ]
        return {"found": True, "title": title, "sections": sections}
    except Exception as e:
        return {"found": False, "title": title, "sections": [], "error": str(e)}


def get_related(title: str, max_results: int = 5) -> dict:
    """Get articles related to a Wikipedia page.

    Returns:
      {"results": list[{"title": str, "description": str, "url": str}]}
    """
    try:
        encoded = quote_plus(title.replace(" ", "_"))
        resp = httpx.get(f"{BASE_API}/page/related/{encoded}", timeout=TIMEOUT)
        resp.raise_for_status()
        pages = resp.json().get("pages", [])[:max_results]
        results = [
            {
                "title": p.get("title", ""),
                "description": p.get("description", ""),
                "url": p.get("content_urls", {}).get("desktop", {}).get("page", ""),
            }
            for p in pages
        ]
        return {"results": results, "error": None}
    except Exception as e:
        return {"results": [], "error": str(e)}
