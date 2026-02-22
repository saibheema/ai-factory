"""Tavily web research tool — search the web for best practices, OSS tools, etc."""

import logging
import os

import httpx

log = logging.getLogger(__name__)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
TAVILY_URL = "https://api.tavily.com/search"


def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web using Tavily API.

    Returns: {"query": str, "results": [{"title", "url", "snippet"}], "answer": str}
    """
    if not TAVILY_API_KEY:
        log.warning("TAVILY_API_KEY not set — returning empty results")
        return {"query": query, "results": [], "answer": f"[Research needed: {query}]"}

    try:
        resp = httpx.post(
            TAVILY_URL,
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "max_results": max_results,
                "search_depth": "advanced",
                "include_answer": True,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        results = [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")[:300]}
            for r in data.get("results", [])
        ]

        log.info("Tavily search: %s → %d results", query, len(results))
        return {
            "query": query,
            "results": results,
            "answer": data.get("answer", ""),
        }
    except Exception as e:
        log.warning("Tavily search failed: %s", e)
        return {"query": query, "results": [], "answer": f"[Search failed: {e}]"}
