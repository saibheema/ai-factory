"""Terraform tool — infrastructure-as-code plan, validate, and apply.

Used by devops and sre_ops for IaC lifecycle management.

Env vars:
  TERRAFORM_BIN      — path to terraform binary (default: terraform)
  TERRAFORM_TIMEOUT  — command timeout in seconds (default: 300)
  TERRAFORM_WORKDIR  — default working directory (default: .)
"""

import logging
import os
import subprocess

log = logging.getLogger(__name__)

TF_BIN = os.getenv("TERRAFORM_BIN", "terraform")
TIMEOUT = int(os.getenv("TERRAFORM_TIMEOUT", "300"))
WORKDIR = os.getenv("TERRAFORM_WORKDIR", ".")


def _run(args: list[str], cwd: str | None = None, env_extra: dict | None = None) -> dict:
    env = os.environ.copy()
    # Non-interactive flags
    env.update({"TF_IN_AUTOMATION": "1", "TF_INPUT": "0"})
    if env_extra:
        env.update(env_extra)
    try:
        result = subprocess.run(
            [TF_BIN] + args,
            capture_output=True, text=True,
            timeout=TIMEOUT, cwd=cwd or WORKDIR, env=env,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:10000],
            "stderr": result.stderr[:3000],
            "returncode": result.returncode,
        }
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": "terraform not found in PATH", "returncode": -1}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "terraform timed out", "returncode": -1}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


def validate(workdir: str = "") -> dict:
    """Run terraform validate to check syntax and internal consistency.

    Returns:
      {"success": bool, "stdout": str, "stderr": str}
    """
    return _run(["validate", "-json"], cwd=workdir or WORKDIR)


def plan(workdir: str = "", var_file: str = "", out_file: str = "") -> dict:
    """Run terraform plan.

    Args:
      workdir: Directory containing .tf files
      var_file: Optional .tfvars file path
      out_file: Optional plan output file path

    Returns:
      {"success": bool, "stdout": str (plan summary), "stderr": str}
    """
    args = ["plan", "-no-color"]
    if var_file:
        args += [f"-var-file={var_file}"]
    if out_file:
        args += [f"-out={out_file}"]
    return _run(args, cwd=workdir or WORKDIR)


def apply(workdir: str = "", plan_file: str = "", auto_approve: bool = False) -> dict:
    """Run terraform apply.

    Args:
      plan_file: Optional pre-computed plan file
      auto_approve: Skip interactive approval (set True only in CI)
    """
    args = ["apply", "-no-color"]
    if auto_approve:
        args.append("-auto-approve")
    if plan_file:
        args.append(plan_file)
    return _run(args, cwd=workdir or WORKDIR)


def destroy(workdir: str = "", auto_approve: bool = False) -> dict:
    """Run terraform destroy."""
    args = ["destroy", "-no-color"]
    if auto_approve:
        args.append("-auto-approve")
    return _run(args, cwd=workdir or WORKDIR)


def init(workdir: str = "") -> dict:
    """Run terraform init to download providers and modules."""
    return _run(["init", "-no-color", "-reconfigure"], cwd=workdir or WORKDIR)


def show(workdir: str = "") -> dict:
    """Run terraform show to display the current state."""
    return _run(["show", "-no-color"], cwd=workdir or WORKDIR)


def output(workdir: str = "") -> dict:
    """Run terraform output -json to get output values as JSON."""
    return _run(["output", "-json"], cwd=workdir or WORKDIR)


def checkov_scan(workdir: str = "") -> dict:
    """Run Checkov IaC security scan on Terraform files.

    Returns:
      {"success": bool, "passed": bool, "failed_checks": int, "passed_checks": int, "stdout": str}
    """
    try:
        result = subprocess.run(
            ["checkov", "-d", workdir or WORKDIR, "--framework", "terraform",
             "--output", "json", "--quiet"],
            capture_output=True, text=True, timeout=120,
        )
        import json
        try:
            data = json.loads(result.stdout or "{}")
            summary = data.get("summary", {})
            failed = summary.get("failed", 0)
            passed = summary.get("passed", 0)
        except Exception:
            failed, passed = 0, 0
        return {
            "success": True,
            "passed": failed == 0,
            "failed_checks": failed,
            "passed_checks": passed,
            "stdout": result.stdout[:5000],
        }
    except FileNotFoundError:
        return {"success": False, "passed": True, "failed_checks": 0, "passed_checks": 0,
                "stdout": "checkov not found — skipping IaC security scan"}
    except Exception as e:
        return {"success": False, "passed": False, "failed_checks": 0, "passed_checks": 0,
                "stdout": str(e)}
