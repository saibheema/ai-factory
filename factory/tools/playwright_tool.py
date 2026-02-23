"""Playwright tool — headless browser automation and E2E testing.

Used by qa_eng and frontend_eng for end-to-end tests,
accessibility checks, screenshot regression, and web scraping.

Env vars:
  PLAYWRIGHT_HEADLESS  — "true" (default) | "false"
  PLAYWRIGHT_TIMEOUT   — ms, default 30000
  PLAYWRIGHT_BROWSER   — chromium | firefox | webkit (default: chromium)
"""

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() != "false"
TIMEOUT = int(os.getenv("PLAYWRIGHT_TIMEOUT", "30000"))
BROWSER_TYPE = os.getenv("PLAYWRIGHT_BROWSER", "chromium")


def _run(coro):
    """Run async coroutine from sync context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _launch():
    try:
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        browser_factory = getattr(pw, BROWSER_TYPE)
        browser = await browser_factory.launch(headless=HEADLESS)
        return pw, browser
    except ImportError:
        raise RuntimeError("playwright not installed — run: pip install playwright && playwright install")


def screenshot(url: str, output_path: str = "", selector: str = "") -> dict:
    """Take a screenshot of a URL.

    Args:
      url:         Page URL
      output_path: Save path (default: tempfile .png)
      selector:    Optional CSS selector to screenshot just that element

    Returns:
      {"success": bool, "path": str, "error": str|None}
    """
    async def _inner():
        pw, browser = await _launch()
        try:
            page = await browser.new_page()
            page.set_default_timeout(TIMEOUT)
            await page.goto(url)
            path = output_path or tempfile.mktemp(suffix=".png")
            if selector:
                el = await page.query_selector(selector)
                if el:
                    await el.screenshot(path=path)
                else:
                    await page.screenshot(path=path, full_page=True)
            else:
                await page.screenshot(path=path, full_page=True)
            return {"success": True, "path": path, "error": None}
        except Exception as e:
            return {"success": False, "path": "", "error": str(e)}
        finally:
            await browser.close()
            await pw.stop()

    try:
        return _run(_inner())
    except Exception as e:
        return {"success": False, "path": "", "error": str(e)}


def get_page_text(url: str, selector: str = "body") -> dict:
    """Fetch visible text from a URL.

    Returns:
      {"success": bool, "text": str, "title": str, "error": str|None}
    """
    async def _inner():
        pw, browser = await _launch()
        try:
            page = await browser.new_page()
            page.set_default_timeout(TIMEOUT)
            await page.goto(url)
            title = await page.title()
            el = await page.query_selector(selector)
            text = await el.inner_text() if el else ""
            return {"success": True, "text": text[:5000], "title": title, "error": None}
        except Exception as e:
            return {"success": False, "text": "", "title": "", "error": str(e)}
        finally:
            await browser.close()
            await pw.stop()

    try:
        return _run(_inner())
    except Exception as e:
        return {"success": False, "text": "", "title": "", "error": str(e)}


def check_accessibility(url: str) -> dict:
    """Run a basic accessibility audit using axe-core via Playwright.

    Returns:
      {"success": bool, "violation_count": int, "violations": list, "error": str|None}
    """
    axe_cdn = "https://cdn.jsdelivr.net/npm/axe-core@4.8.0/axe.min.js"

    async def _inner():
        pw, browser = await _launch()
        try:
            page = await browser.new_page()
            page.set_default_timeout(TIMEOUT)
            await page.goto(url)
            await page.add_script_tag(url=axe_cdn)
            results = await page.evaluate("() => axe.run().then(r => r)")
            violations = results.get("violations", [])
            simplified = [
                {"id": v["id"], "impact": v["impact"], "description": v["description"], "count": len(v.get("nodes", []))}
                for v in violations
            ]
            return {
                "success": True,
                "violation_count": len(violations),
                "violations": simplified[:20],
                "error": None,
            }
        except Exception as e:
            return {"success": False, "violation_count": 0, "violations": [], "error": str(e)}
        finally:
            await browser.close()
            await pw.stop()

    try:
        return _run(_inner())
    except Exception as e:
        return {"success": False, "violation_count": 0, "violations": [], "error": str(e)}


def run_e2e_script(script_py: str) -> dict:
    """Execute an arbitrary async Playwright script string.

    The script must define an async function `run(page)` that accepts a Playwright page.

    Example script:
      async def run(page):
          await page.goto("https://example.com")
          return {"title": await page.title()}

    Returns:
      {"success": bool, "result": any, "error": str|None}
    """
    async def _inner():
        pw, browser = await _launch()
        try:
            page = await browser.new_page()
            page.set_default_timeout(TIMEOUT)
            ns: dict = {}
            exec(script_py, ns)  # noqa: S102
            run_fn = ns.get("run")
            if not callable(run_fn):
                return {"success": False, "result": None, "error": "Script must define async def run(page)"}
            result = await run_fn(page)
            return {"success": True, "result": result, "error": None}
        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}
        finally:
            await browser.close()
            await pw.stop()

    try:
        return _run(_inner())
    except Exception as e:
        return {"success": False, "result": None, "error": str(e)}


def check_links(base_url: str, max_links: int = 50) -> dict:
    """Crawl a page and check all internal links for HTTP errors.

    Returns:
      {"success": bool, "total": int, "broken": list[{"url":str,"status":int}], "error": str|None}
    """
    async def _inner():
        pw, browser = await _launch()
        try:
            page = await browser.new_page()
            page.set_default_timeout(TIMEOUT)
            await page.goto(base_url)
            hrefs = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            from urllib.parse import urlparse
            base_domain = urlparse(base_url).netloc
            internal = list({h for h in hrefs if urlparse(h).netloc == base_domain})[:max_links]
            broken = []
            for link in internal:
                try:
                    r = await page.request.get(link)
                    if r.status >= 400:
                        broken.append({"url": link, "status": r.status})
                except Exception:
                    broken.append({"url": link, "status": -1})
            return {"success": True, "total": len(internal), "broken": broken, "error": None}
        except Exception as e:
            return {"success": False, "total": 0, "broken": [], "error": str(e)}
        finally:
            await browser.close()
            await pw.stop()

    try:
        return _run(_inner())
    except Exception as e:
        return {"success": False, "total": 0, "broken": [], "error": str(e)}
