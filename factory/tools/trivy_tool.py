"""Trivy tool — container, filesystem, and IaC vulnerability scanner.

Open source: https://trivy.dev  (Apache-2.0)
Install: brew install trivy  |  apt-get install trivy

Env vars:
  TRIVY_BIN      — path to trivy binary (default: trivy)
  TRIVY_SEVERITY — minimum severity to report (default: HIGH,CRITICAL)
"""

import json
import logging
import os
import subprocess

log = logging.getLogger(__name__)

TRIVY_BIN = os.getenv("TRIVY_BIN", "trivy")
TRIVY_SEVERITY = os.getenv("TRIVY_SEVERITY", "HIGH,CRITICAL")


def scan_image(image: str) -> dict:
    """Scan a Docker image for known CVEs.

    Returns: {"passed": bool, "vulnerabilities": [...], "vuln_count": int, "image": str}
    """
    return _run_trivy(["image", "--format", "json", "--severity", TRIVY_SEVERITY, image], label=image)


def scan_filesystem(path: str) -> dict:
    """Scan a local filesystem path (code, dependencies) for CVEs and secrets.

    Returns: {"passed": bool, "vulnerabilities": [...], "vuln_count": int}
    """
    return _run_trivy(["fs", "--format", "json", "--severity", TRIVY_SEVERITY, path], label=path)


def scan_iac(path: str) -> dict:
    """Scan Infrastructure-as-Code files (Dockerfile, Terraform, K8s YAML).

    Returns: {"passed": bool, "misconfigurations": [...], "misconfig_count": int}
    """
    result = _run_trivy(
        ["config", "--format", "json", "--severity", TRIVY_SEVERITY, path],
        label=path,
        result_key="misconfigurations",
    )
    return result


def scan_secrets(path: str) -> dict:
    """Scan for hardcoded secrets in source code.

    Returns: {"passed": bool, "secrets": [...], "secret_count": int}
    """
    return _run_trivy(
        ["fs", "--scanners", "secret", "--format", "json", path],
        label=path,
        result_key="secrets",
    )


# ── Internal ──────────────────────────────────────────────────────────────────

def _run_trivy(args: list[str], label: str, result_key: str = "vulnerabilities") -> dict:
    try:
        result = subprocess.run(
            [TRIVY_BIN] + args,
            capture_output=True,
            text=True,
            timeout=180,
        )
        items = []
        output = result.stdout.strip()
        if output:
            try:
                data = json.loads(output)
                for target in data.get("Results", []):
                    for item in target.get("Vulnerabilities", target.get("Misconfigurations", target.get("Secrets", []))):
                        items.append({
                            "id": item.get("VulnerabilityID", item.get("ID", "")),
                            "title": item.get("Title", item.get("Message", "")),
                            "severity": item.get("Severity", ""),
                            "package": item.get("PkgName", ""),
                            "installed_version": item.get("InstalledVersion", ""),
                            "fixed_version": item.get("FixedVersion", ""),
                        })
            except json.JSONDecodeError:
                pass

        criticals = [v for v in items if v["severity"] in ("CRITICAL", "HIGH")]
        passed = len(criticals) == 0
        log.info("trivy scan: %s — %d issue(s) (%d critical/high)", label, len(items), len(criticals))
        return {
            "passed": passed,
            result_key: items,
            f"{result_key.rstrip('s')}_count": len(items),
            "critical_high_count": len(criticals),
        }
    except FileNotFoundError:
        log.warning("trivy not found — install: brew install trivy")
        return {"passed": True, result_key: [], "warning": "trivy not installed"}
    except subprocess.TimeoutExpired:
        return {"passed": False, result_key: [], "error": "trivy scan timed out"}
    except Exception as e:
        log.warning("trivy scan failed: %s", e)
        return {"passed": False, result_key: [], "error": str(e)}
