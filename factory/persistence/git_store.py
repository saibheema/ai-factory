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


class GitArtifactStore:
    """Push pipeline artifacts to a user's Git repository."""

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
        tmpdir = tempfile.mkdtemp(prefix="aifactory-git-")
        try:
            auth_url = self._inject_token(git_url, git_token)

            # Clone (shallow)
            self._run(["git", "clone", "--depth", "1", auth_url, tmpdir])

            # Re-set remote origin to auth URL so push also works
            self._run(["git", "remote", "set-url", "origin", auth_url], cwd=tmpdir)

            # Create branch
            short_task = task_id[:12] if len(task_id) > 12 else task_id
            branch = f"ai-factory/{project_id}/{short_task}"
            self._run(["git", "checkout", "-b", branch], cwd=tmpdir)

            # Write artifacts
            out_dir = os.path.join(tmpdir, "ai-factory-output", project_id, short_task)
            os.makedirs(out_dir, exist_ok=True)

            # README with summary
            readme = f"# AI Factory Output\n\n"
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

            # Commit and push
            env = {
                "GIT_AUTHOR_NAME": "AI Factory",
                "GIT_AUTHOR_EMAIL": "ai-factory@unicon.ai",
                "GIT_COMMITTER_NAME": "AI Factory",
                "GIT_COMMITTER_EMAIL": "ai-factory@unicon.ai",
            }
            self._run(["git", "add", "."], cwd=tmpdir)
            self._run(
                ["git", "commit", "-m", f"AI Factory: {project_id} - {requirement[:80]}"],
                cwd=tmpdir,
                env=env,
            )
            self._run(["git", "push", "origin", branch], cwd=tmpdir)

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
