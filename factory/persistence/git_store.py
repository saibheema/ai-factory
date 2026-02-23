"""Git integration — push pipeline artifacts to user's repository.

When a user provides a Git URL + token for their project, pipeline
artifacts are committed to a new branch and pushed instead of being
stored in GCS.
"""

import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime


# Git env that prevents any interactive prompts (safe for Cloud Run / CI)
_GIT_NONINTERACTIVE_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "echo",
    "GCM_INTERACTIVE": "never",
}


class GitArtifactStore:
    """Push pipeline artifacts to a user's Git repository."""

    def fetch_repo_tree(self, git_url: str, git_token: str, branch: str = "main", max_files: int = 60) -> list[dict]:
        """Fetch the repo file tree + contents of key files for learning."""
        try:
            tree_raw = self._github(git_url, git_token, "GET", f"git/trees/{branch}?recursive=1")
            tree = tree_raw.get("tree", []) if isinstance(tree_raw, dict) else []
            # Filter to code files, skip binaries/images/node_modules
            _SKIP = {'.png','.jpg','.jpeg','.gif','.ico','.svg','.woff','.woff2','.ttf','.eot','.mp4','.zip','.gz','.tar','.lock'}
            _SKIP_DIRS = {'node_modules/', '.git/', 'dist/', 'build/', '__pycache__/', '.next/', 'vendor/'}
            files = []
            for item in tree:
                if item.get('type') != 'blob':
                    continue
                path = item.get('path', '')
                if any(path.startswith(d) or f'/{d}' in path for d in _SKIP_DIRS):
                    continue
                ext = '.' + path.rsplit('.', 1)[-1] if '.' in path else ''
                if ext.lower() in _SKIP:
                    continue
                files.append({'path': path, 'sha': item.get('sha', ''), 'size': item.get('size', 0)})
            # Fetch content of key files (README, package.json, main source, etc.)
            results = []
            fetched = 0
            for f in sorted(files, key=lambda x: (0 if x['path'].lower() in ('readme.md','package.json','pyproject.toml','requirements.txt','dockerfile') else 1, x['size'])):
                if fetched >= max_files:
                    break
                if f['size'] > 50000:  # skip very large files
                    results.append({'path': f['path'], 'content': f'(file too large: {f["size"]} bytes)', 'size': f['size']})
                    fetched += 1
                    continue
                try:
                    blob = self._github(git_url, git_token, "GET", f"git/blobs/{f['sha']}")
                    import base64
                    content = base64.b64decode(blob.get('content', '')).decode('utf-8', errors='replace') if blob.get('encoding') == 'base64' else blob.get('content', '')
                    results.append({'path': f['path'], 'content': content[:8000], 'size': f['size']})
                except Exception:
                    results.append({'path': f['path'], 'content': '(fetch failed)', 'size': f['size']})
                fetched += 1
            return results
        except Exception as exc:
            return [{'path': 'error', 'content': str(exc), 'size': 0}]

    def push_artifacts(
        self,
        git_url: str,
        git_token: str,
        project_id: str,
        task_id: str,
        requirement: str,
        artifacts: dict[str, str],
    ) -> dict:
        """Clone repo, write artifacts, commit, push. Returns status dict."""
        # Fall back to env-level token if caller didn't supply one
        if not git_token:
            git_token = os.environ.get("GITHUB_TOKEN", "")

        if not git_token:
            return {
                "status": "failed",
                "error": (
                    "No git token available. Set GITHUB_TOKEN env var "
                    "or pass git_token in the request."
                ),
            }

        tmpdir = tempfile.mkdtemp(prefix="aifactory-git-")
        try:
            auth_url = self._inject_token(git_url, git_token)

            # Clone (shallow) — use auth URL + non-interactive env
            self._run(["git", "clone", "--depth", "1", auth_url, tmpdir])

            # Re-set remote origin to auth URL so push also uses it
            self._run(["git", "remote", "set-url", "origin", auth_url], cwd=tmpdir)

            # Create branch
            short_task = task_id[:12] if len(task_id) > 12 else task_id
            branch = f"ai-factory/{project_id}/{short_task}"
            self._run(["git", "checkout", "-b", branch], cwd=tmpdir)

            # Write artifacts
            out_dir = os.path.join(tmpdir, "ai-factory-output", project_id, short_task)
            os.makedirs(out_dir, exist_ok=True)

            # README with summary
            readme = "# AI Factory Output\n\n"
            readme += f"**Project:** {project_id}  \n"
            readme += f"**Task:** {task_id}  \n"
            readme += f"**Requirement:** {requirement}  \n"
            readme += f"**Generated:** {datetime.now(UTC).isoformat()}  \n\n"
            readme += "## Teams\n\n"
            for team in artifacts:
                readme += f"- [{team}](./{team}.md)\n"
            with open(os.path.join(out_dir, "README.md"), "w") as f:
                f.write(readme)

            # Per-team artifact files
            for team, artifact in artifacts.items():
                path = os.path.join(out_dir, f"{team}.md")
                with open(path, "w") as f:
                    f.write(f"# {team}\n\n```\n{artifact}\n```\n")

            # Commit and push — include identity + non-interactive guards
            git_env = {
                "GIT_AUTHOR_NAME": "AI Factory",
                "GIT_AUTHOR_EMAIL": "ai-factory@unicon.ai",
                "GIT_COMMITTER_NAME": "AI Factory",
                "GIT_COMMITTER_EMAIL": "ai-factory@unicon.ai",
                **_GIT_NONINTERACTIVE_ENV,
            }
            self._run(["git", "add", "."], cwd=tmpdir, env=git_env)
            self._run(
                ["git", "commit", "-m", f"AI Factory: {project_id} - {requirement[:80]}"],
                cwd=tmpdir,
                env=git_env,
            )
            self._run(
                ["git", "push", "--set-upstream", "origin", branch],
                cwd=tmpdir,
                env=git_env,
            )

            return {
                "status": "pushed",
                "branch": branch,
                "files": len(artifacts) + 1,
                "git_url": git_url,
            }
        except Exception as e:
            return {"status": "failed", "error": str(e)}
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ── internal helpers ─────────────────────────────────────
    # ── GitHub REST API helpers ───────────────────────────────────────────

    @staticmethod
    def _parse_github_repo(git_url: str) -> tuple[str, str]:
        """Return (owner, repo) from a GitHub HTTPS or SSH URL."""
        import re
        m = re.search(r'github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?$', git_url)
        if not m:
            raise ValueError(f"Not a GitHub URL: {git_url}")
        return m.group(1), m.group(2)

    def _github(self, git_url: str, git_token: str,
                method: str, endpoint: str,
                body: dict | None = None) -> dict | list:
        """Make a GitHub REST API call."""
        import httpx
        owner, repo = self._parse_github_repo(git_url)
        url = f"https://api.github.com/repos/{owner}/{repo}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {git_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        with httpx.Client(timeout=15.0) as client:
            if method == "GET":
                resp = client.get(url, headers=headers)
            elif method == "POST":
                resp = client.post(url, headers=headers, json=body or {})
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
        resp.raise_for_status()
        return resp.json() if resp.text else {}

    def list_branches(self, git_url: str, git_token: str) -> list[dict]:
        """List repo branches with metadata via GitHub API."""
        try:
            raw: list = self._github(  # type: ignore[assignment]
                git_url, git_token, "GET",
                "branches?per_page=50&protected=false",
            )
            branches = []
            for b in (raw if isinstance(raw, list) else []):
                name: str = b.get("name", "")
                sha: str = (b.get("commit") or {}).get("sha", "")
                branches.append({
                    "name": name,
                    "sha": sha[:8] if sha else "",
                    "full_sha": sha,
                    "protected": b.get("protected", False),
                    "is_ai": name.startswith("ai-factory/"),
                })
            return branches
        except Exception as exc:
            return [{"name": "error", "sha": "", "is_ai": False,
                     "protected": False, "error": str(exc)}]

    def merge_all_ai_branches(
        self,
        git_url: str,
        git_token: str,
        target_branch: str = "main",
    ) -> dict:
        """Find every ai-factory/* branch and merge it into target_branch.

        Returns a summary dict: {merged: [...], skipped: [...], failed: [...]}
        """
        merged, skipped, failed = [], [], []
        try:
            branches = self.list_branches(git_url, git_token)
            ai_branches = [b for b in branches if b.get("is_ai") and not b.get("protected") and b.get("name") != target_branch]
            for b in ai_branches:
                result = self.merge_branch(
                    git_url=git_url,
                    git_token=git_token,
                    source_branch=b["name"],
                    target_branch=target_branch,
                )
                if result["status"] == "merged":
                    merged.append(b["name"])
                elif result["status"] == "already_merged":
                    skipped.append(b["name"])
                else:
                    failed.append({"branch": b["name"], "error": result.get("error", "")})
        except Exception as exc:
            failed.append({"branch": "*", "error": str(exc)})
        return {
            "merged": merged,
            "skipped": skipped,
            "failed": failed,
            "total_ai_branches": len(merged) + len(skipped) + len(failed),
        }

    def merge_branch(
        self,
        git_url: str,
        git_token: str,
        source_branch: str,
        target_branch: str = "main",
    ) -> dict:
        """Merge source_branch into target_branch via GitHub API."""
        try:
            result = self._github(
                git_url, git_token, "POST", "merges",
                body={
                    "base": target_branch,
                    "head": source_branch,
                    "commit_message":
                        f"AI Factory: merge '{source_branch}' → '{target_branch}'",
                },
            )
            sha = ""
            if isinstance(result, dict):
                sha = (result.get("sha") or "")[:8]
            return {
                "status": "merged",
                "source": source_branch,
                "target": target_branch,
                "sha": sha,
            }
        except Exception as exc:
            # GitHub returns 204 when already up-to-date
            if "204" in str(exc) or "No Content" in str(exc):
                return {
                    "status": "already_merged",
                    "source": source_branch,
                    "target": target_branch,
                    "sha": "",
                }
            return {
                "status": "failed",
                "source": source_branch,
                "target": target_branch,
                "error": str(exc),
            }

    # ── internal helpers ─────────────────────────────────────────────────

    @staticmethod
    def _inject_token(url: str, token: str) -> str:
        """Insert a Personal Access Token into an HTTPS git URL."""
        if not token:
            return url
        # Strip any existing credentials first
        if "@" in url and "://" in url:
            scheme, rest = url.split("://", 1)
            rest = rest.split("@", 1)[1]  # drop existing user:pass@
            url = f"{scheme}://{rest}"
        if url.startswith("https://"):
            return url.replace("https://", f"https://x-access-token:{token}@")
        if url.startswith("http://"):
            return url.replace("http://", f"http://x-access-token:{token}@")
        return url

    @staticmethod
    def _run(cmd: list[str], cwd: str | None = None, env: dict | None = None) -> str:
        full_env = dict(os.environ)
        # Always disable interactive prompts (Cloud Run has no TTY)
        full_env.update(_GIT_NONINTERACTIVE_ENV)
        if env:
            full_env.update(env)
        result = subprocess.run(
            cmd,
            cwd=cwd,
            env=full_env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git failed: {' '.join(cmd)}\n{result.stderr}")
        return result.stdout
