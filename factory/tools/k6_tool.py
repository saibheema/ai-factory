"""k6 load testing tool — generate and run k6 performance tests.

Used by qa_eng and sre_ops teams for API load testing and SLO validation.

Env vars:
  K6_BIN      — path to k6 binary (default: k6)
  K6_TIMEOUT  — max seconds to wait for test (default: 120)
  K6_VUS      — default virtual users (default: 10)
  K6_DURATION — default test duration (default: 30s)
"""

import logging
import os
import subprocess
import tempfile

log = logging.getLogger(__name__)

K6_BIN = os.getenv("K6_BIN", "k6")
TIMEOUT = int(os.getenv("K6_TIMEOUT", "120"))
DEFAULT_VUS = int(os.getenv("K6_VUS", "10"))
DEFAULT_DURATION = os.getenv("K6_DURATION", "30s")


def _run_k6(script_path: str, vus: int, duration: str, env_vars: dict | None = None) -> dict:
    """Execute a k6 test script."""
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)
    try:
        result = subprocess.run(
            [K6_BIN, "run", "--vus", str(vus), "--duration", duration,
             "--summary-export", "/tmp/k6-summary.json", script_path],
            capture_output=True, text=True, timeout=TIMEOUT, env=env,
        )
        summary = _read_summary()
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:6000],
            "stderr": result.stderr[:2000],
            "returncode": result.returncode,
            "summary": summary,
        }
    except FileNotFoundError:
        return {
            "success": False, "stdout": "", "stderr": "k6 not found in PATH",
            "returncode": -1, "summary": {},
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False, "stdout": "", "stderr": "k6 test timed out",
            "returncode": -1, "summary": {},
        }
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1, "summary": {}}


def _read_summary() -> dict:
    try:
        import json
        with open("/tmp/k6-summary.json") as f:
            return json.load(f)
    except Exception:
        return {}


def run_script(script_js: str, vus: int = 0, duration: str = "") -> dict:
    """Run an arbitrary k6 JavaScript test script.

    Args:
      script_js: The k6 test script content (JavaScript)
      vus: Number of virtual users (default: K6_VUS env or 10)
      duration: Test duration (default: K6_DURATION env or 30s)

    Returns:
      {"success": bool, "stdout": str, "summary": dict}
    """
    with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
        f.write(script_js)
        tmp_path = f.name
    try:
        return _run_k6(tmp_path, vus or DEFAULT_VUS, duration or DEFAULT_DURATION)
    finally:
        os.unlink(tmp_path)


def load_test_http(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    body: str = "",
    vus: int = 0,
    duration: str = "",
    thresholds: dict | None = None,
) -> dict:
    """Generate and run a k6 HTTP load test for a given endpoint.

    Args:
      url:        Target URL
      method:     HTTP method
      headers:    Request headers dict
      body:       Request body string (for POST/PUT)
      thresholds: k6 threshold dict e.g. {"http_req_duration": ["p(95)<500"]}

    Returns:
      {"success": bool, "passed": bool, "p95_ms": float, "rps": float, "error_rate": float, "summary": dict}
    """
    import json as _json
    hdr_str = _json.dumps(headers or {})
    body_str = f'"{body}"' if body else '""'
    threshold_str = _json.dumps(thresholds or {"http_req_duration": ["p(95)<2000"], "http_req_failed": ["rate<0.05"]})

    script = f"""
import http from 'k6/http';
import {{ check, sleep }} from 'k6';

export let options = {{
  vus: {vus or DEFAULT_VUS},
  duration: '{duration or DEFAULT_DURATION}',
  thresholds: {threshold_str},
}};

export default function() {{
  const headers = {hdr_str};
  const body = {body_str};
  const res = http.{method.lower()}('{url}', body || null, {{ headers }});
  check(res, {{
    'status is 2xx': (r) => r.status >= 200 && r.status < 300,
    'duration < 2s': (r) => r.timings.duration < 2000,
  }});
  sleep(0.1);
}}
"""
    result = run_script(script, vus=vus or DEFAULT_VUS, duration=duration or DEFAULT_DURATION)

    # Parse key metrics
    summary = result.get("summary", {})
    metrics = summary.get("metrics", {})
    p95 = (metrics.get("http_req_duration", {}).get("values", {}).get("p(95)") or 0)
    rps = (metrics.get("http_reqs", {}).get("values", {}).get("rate") or 0)
    error_rate = (metrics.get("http_req_failed", {}).get("values", {}).get("rate") or 0)

    return {
        "success": result["success"],
        "passed": result["returncode"] == 0,
        "p95_ms": round(p95, 2),
        "rps": round(rps, 2),
        "error_rate": round(error_rate * 100, 2),
        "stdout": result["stdout"],
        "summary": summary,
    }


def smoke_test(base_url: str, endpoints: list[str] | None = None) -> dict:
    """Run a lightweight smoke test (1 VU, 10s) against a list of endpoints.

    Returns:
      {"success": bool, "results": list[dict]}
    """
    targets = endpoints or ["/health", "/"]
    results = []
    for path in targets:
        url = f"{base_url.rstrip('/')}{path}"
        r = load_test_http(url, vus=1, duration="10s",
                           thresholds={"http_req_failed": ["rate<0.01"]})
        results.append({"endpoint": path, "passed": r["passed"], "p95_ms": r["p95_ms"]})
    overall = all(r["passed"] for r in results)
    return {"success": True, "passed": overall, "results": results}
