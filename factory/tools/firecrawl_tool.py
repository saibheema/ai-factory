"""Firecrawl tool — web scraping and site crawling via the Firecrawl API.

Used by product_mgmt and biz_analysis teams to gather competitive
intelligence, scrape documentation, and extract structured data from websites.

Env vars:
  FIRECRAWL_API_KEY  — Firecrawl API key (get one at firecrawl.dev)
  FIRECRAWL_BASE_URL — API base (default: https://api.firecrawl.dev/v1)
  FIRECRAWL_TIMEOUT  — HTTP timeout seconds (default: 60)
"""

import logging
import os
import time

import httpx

log = logging.getLogger(__name__)

API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
BASE_URL = os.getenv("FIRECRAWL_BASE_URL", "https://api.firecrawl.dev/v1")
TIMEOUT = int(os.getenv("FIRECRAWL_TIMEOUT", "60"))


def _headers() -> dict:
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def _available() -> bool:
    return bool(API_KEY)


def scrape_url(url: str, formats: list[str] | None = None) -> dict:
    """Scrape a single URL and return clean markdown/HTML.

    Args:
      url:     URL to scrape
      formats: ["markdown", "html", "rawHtml", "screenshot"] — default: ["markdown"]

    Returns:
      {"success": bool, "markdown": str, "html": str, "metadata": dict, "error": str|None}
    """
    if not _available():
        return {"success": False, "markdown": "", "html": "",
                "metadata": {}, "error": "FIRECRAWL_API_KEY not set"}
    payload = {"url": url, "formats": formats or ["markdown"]}
    try:
        resp = httpx.post(f"{BASE_URL}/scrape", headers=_headers(), json=payload, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            return {
                "success": True,
                "markdown": data.get("markdown", "")[:10000],
                "html": data.get("html", "")[:5000],
                "metadata": data.get("metadata", {}),
                "error": None,
            }
        return {"success": False, "markdown": "", "html": "",
                "metadata": {}, "error": f"HTTP {resp.status_code}: {resp.text[:300]}"}
    except Exception as e:
        return {"success": False, "markdown": "", "html": "", "metadata": {}, "error": str(e)}


def crawl_site(url: str, max_pages: int = 20, include_paths: list[str] | None = None,
               exclude_paths: list[str] | None = None) -> dict:
    """Crawl a website and return content from multiple pages.

    This uses Firecrawl's async crawl API (starts job, polls for completion).

    Args:
      url:           Root URL to start crawling from
      max_pages:     Maximum pages to crawl (default 20)
      include_paths: URL path patterns to include (e.g. ["/docs/*"])
      exclude_paths: URL path patterns to exclude (e.g. ["/blog/*"])

    Returns:
      {"success": bool, "pages": list[{"url": str, "markdown": str}],
       "page_count": int, "error": str|None}
    """
    if not _available():
        return {"success": False, "pages": [], "page_count": 0,
                "error": "FIRECRAWL_API_KEY not set"}
    payload: dict = {
        "url": url,
        "limit": max_pages,
        "scrapeOptions": {"formats": ["markdown"]},
    }
    if include_paths:
        payload["includePaths"] = include_paths
    if exclude_paths:
        payload["excludePaths"] = exclude_paths

    try:
        # Start crawl job
        start_resp = httpx.post(f"{BASE_URL}/crawl", headers=_headers(), json=payload, timeout=30)
        if start_resp.status_code != 200:
            return {"success": False, "pages": [], "page_count": 0,
                    "error": f"HTTP {start_resp.status_code}: {start_resp.text[:300]}"}
        job_id = start_resp.json().get("id", "")
        if not job_id:
            return {"success": False, "pages": [], "page_count": 0, "error": "No job ID returned"}

        # Poll for completion
        for _ in range(30):  # max 5 min
            time.sleep(10)
            status_resp = httpx.get(f"{BASE_URL}/crawl/{job_id}", headers=_headers(), timeout=15)
            if status_resp.status_code != 200:
                continue
            status_data = status_resp.json()
            if status_data.get("status") == "completed":
                pages = [
                    {"url": p.get("metadata", {}).get("url", ""), "markdown": p.get("markdown", "")[:5000]}
                    for p in status_data.get("data", [])
                ]
                return {"success": True, "pages": pages, "page_count": len(pages), "error": None}
            if status_data.get("status") == "failed":
                return {"success": False, "pages": [], "page_count": 0,
                        "error": status_data.get("error", "Crawl failed")}

        return {"success": False, "pages": [], "page_count": 0, "error": "Crawl job timed out"}
    except Exception as e:
        return {"success": False, "pages": [], "page_count": 0, "error": str(e)}


def extract_structured(url: str, schema: dict, prompt: str = "") -> dict:
    """Extract structured data from a URL using LLM-powered extraction.

    Args:
      url:    URL to scrape
      schema: JSON schema describing the data to extract
      prompt: Optional extraction instructions

    Returns:
      {"success": bool, "data": dict, "error": str|None}
    """
    if not _available():
        return {"success": False, "data": {}, "error": "FIRECRAWL_API_KEY not set"}
    payload: dict = {
        "url": url,
        "formats": ["extract"],
        "extract": {"schema": schema},
    }
    if prompt:
        payload["extract"]["prompt"] = prompt
    try:
        resp = httpx.post(f"{BASE_URL}/scrape", headers=_headers(), json=payload, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json().get("data", {}).get("extract", {})
            return {"success": True, "data": data, "error": None}
        return {"success": False, "data": {}, "error": f"HTTP {resp.status_code}: {resp.text[:300]}"}
    except Exception as e:
        return {"success": False, "data": {}, "error": str(e)}
