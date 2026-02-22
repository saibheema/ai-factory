"""Git tool — push code, configs, and specs to a Git repository.

Wraps the existing GitArtifactStore for per-file operations.
"""

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


def push_files(
    git_url: str,
    git_token: str,
    project_id: str,
    branch_suffix: str,
    files: dict[str, str],
    commit_message: str,
) -> dict:
    """Push a set of files to a Git repository on a feature branch.

    files: {"path/to/file.py": "file content", ...}
    Returns: {"branch": str, "commit": str, "files_pushed": int, "repo_url": str}
    """
    tmp = tempfile.mkdtemp(prefix="aifactory-git-")
    try:
        # Inject token for HTTPS auth
        auth_url = git_url
        if git_token and "://" in git_url:
            # Strip any existing credentials then inject token
            if "@" in git_url:
                scheme, rest = git_url.split("://", 1)
                rest = rest.split("@", 1)[1]
                git_url = f"{scheme}://{rest}"
            if git_url.startswith("https://"):
                auth_url = git_url.replace("https://", f"https://x-access-token:{git_token}@")
            elif git_url.startswith("http://"):
                auth_url = git_url.replace("http://", f"http://x-access-token:{git_token}@")

        # Clone
        subprocess.run(["git", "clone", "--depth", "1", auth_url, tmp], capture_output=True, check=True, timeout=60)
        # Re-set remote so push also carries auth
        subprocess.run(["git", "remote", "set-url", "origin", auth_url], cwd=tmp, capture_output=True, check=True)

        # Create branch
        branch = f"ai-factory/{project_id}/{branch_suffix}"
        subprocess.run(["git", "checkout", "-b", branch], cwd=tmp, capture_output=True, check=True)

        # Write files
        for filepath, content in files.items():
            full_path = Path(tmp) / filepath
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            subprocess.run(["git", "add", filepath], cwd=tmp, capture_output=True, check=True)

        # Commit and push
        subprocess.run(
            ["git", "-c", "user.name=AI Factory", "-c", "user.email=ai-factory@bot", "commit", "-m", commit_message],
            cwd=tmp, capture_output=True, check=True,
        )
        subprocess.run(["git", "push", "origin", branch], cwd=tmp, capture_output=True, check=True, timeout=60)

        # Get commit hash
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp, capture_output=True, text=True)
        commit_hash = result.stdout.strip()[:8]

        log.info("Git push: %d files → %s branch %s", len(files), git_url, branch)
        return {
            "branch": branch,
            "commit": commit_hash,
            "files_pushed": len(files),
            "repo_url": git_url,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def push_code_files(
    git_url: str,
    git_token: str,
    project_id: str,
    team: str,
    files: dict[str, str],
) -> dict:
    """Convenience wrapper for pushing code from a specific team."""
    return push_files(
        git_url=git_url,
        git_token=git_token,
        project_id=project_id,
        branch_suffix=team,
        files=files,
        commit_message=f"[{team}] AI Factory auto-generated code",
    )
