"""AI Factory Orchestrator — v0.3.0

Changes from v0.2:
 • Firebase Authentication on all /api/* routes
 • Firestore persistence (user-scoped projects, memory, settings, runs)
 • GCS artifact storage (default) OR Git push (if user provides repo URL)
 • Project management endpoints (list / create / delete)
 • Git config endpoints per project
 • Run history endpoint
 • Smart team routing — LLM/keyword selector picks only relevant teams
 • Git push auth fixed (x-access-token + remote set-url after clone)
"""

import logging
import os
import threading
import uuid
from collections import defaultdict
from datetime import UTC, datetime

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse, PlainTextResponse

from factory.auth.firebase_auth import AuthUser, get_current_user
from factory.clarification.broker import ClarificationBroker
from factory.agents.phase2_handlers import extract_handoff_to, run_phase2_handler
from factory.agents.task_result import TaskResult
from factory.llm.runtime import TeamLLMRuntime
from factory.pipeline.phase1_pipeline import Phase1Context, Phase1Pipeline
from factory.pipeline.phase2_pipeline import Phase2Context, Phase2Pipeline
from factory.pipeline.project_qa import answer_project_question
from factory.memory.memory_controller import RemoteMemoryController
from factory.observability.incident import IncidentNotifier
from factory.observability.langfuse import LangfuseTracer
from factory.observability.metrics import MetricsRegistry
from factory.tools.registry import phase1_default_tools

log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  App + CORS
# ═══════════════════════════════════════════════════════════
app = FastAPI(title="AI Factory Orchestrator", version="0.2.0")

raw_allowed = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3001,"
    "https://ai-factory-frontend-6slvib5z6a-uc.a.run.app,"
    "https://ai-factory-frontend-664984131730.us-central1.run.app",
)
allowed_origins = [x.strip() for x in raw_allowed.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def _global_exc_handler(request: StarletteRequest, exc: Exception):
    """Convert unhandled exceptions into a proper JSONResponse so the CORS
    middleware can add Access-Control-Allow-Origin headers to error replies."""
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) or "Internal Server Error"},
    )


# ═══════════════════════════════════════════════════════════
#  Shared services (unchanged from v0.1)
# ═══════════════════════════════════════════════════════════
memory = RemoteMemoryController(
    base_url=os.getenv("MEMORY_SERVICE_URL", "http://memory:8006")
)
pipeline = Phase1Pipeline(memory=memory)
llm_runtime = TeamLLMRuntime()
phase2_pipeline = Phase2Pipeline(memory=memory, llm_runtime=llm_runtime)
broker = ClarificationBroker(ttl_seconds=120)
tools = phase1_default_tools()
tracer = LangfuseTracer()
metrics = MetricsRegistry()
incident_notifier = IncidentNotifier()
groupchat_service_url = os.getenv("GROUPCHAT_SERVICE_URL", "http://groupchat:8002")

# ═══════════════════════════════════════════════════════════
#  Lazy-init persistent stores (Firestore / GCS / Git)
# ═══════════════════════════════════════════════════════════
_firestore = None
_gcs = None
_git = None


def _get_firestore():
    global _firestore
    if _firestore is None:
        from factory.persistence.firestore_store import FirestoreStore
        _firestore = FirestoreStore()
    return _firestore


def _get_gcs():
    global _gcs
    if _gcs is None:
        from factory.persistence.gcs_store import GCSArtifactStore
        _gcs = GCSArtifactStore()
    return _gcs


def _get_git():
    global _git
    if _git is None:
        from factory.persistence.git_store import GitArtifactStore
        _git = GitArtifactStore()
    return _git


# ═══════════════════════════════════════════════════════════
#  In-memory task tracker (real-time polling) + Firestore sync
# ═══════════════════════════════════════════════════════════
task_runs: dict[str, dict] = {}
task_runs_lock = threading.Lock()


def _task_store_save(
    task_id: str, payload: dict, uid: str = "", project_id: str = ""
) -> None:
    with task_runs_lock:
        task_runs[task_id] = payload
    if uid and project_id:
        try:
            _get_firestore().save_run(uid, project_id, task_id, payload)
        except Exception:
            log.warning("Firestore save failed for run %s", task_id)


def _task_store_load(task_id: str) -> dict | None:
    with task_runs_lock:
        local = task_runs.get(task_id)
    return local


# ═══════════════════════════════════════════════════════════
#  Request / response models
# ═══════════════════════════════════════════════════════════
class RunRequest(BaseModel):
    project_id: str
    requirement: str


class ClarificationCreateRequest(BaseModel):
    from_team: str = Field(min_length=2)
    to_team: str = Field(min_length=2)
    question: str = Field(min_length=5)


class ClarificationRespondRequest(BaseModel):
    answer: str = Field(min_length=1)


class ProjectQARequest(BaseModel):
    question: str = Field(min_length=4)


class TeamConfigUpdateRequest(BaseModel):
    model: str | None = None
    budget_usd: float | None = Field(default=None, ge=0)
    api_key: str | None = None


class ProjectChatRequest(BaseModel):
    message: str = Field(min_length=2)


class GroupChatRequest(BaseModel):
    topic: str = Field(min_length=3)
    participants: list[str] = Field(default_factory=list)


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    git_url: str | None = None
    git_token: str | None = None


class GitConfigRequest(BaseModel):
    git_url: str = Field(min_length=5)


class UserGitTokenRequest(BaseModel):
    token: str = Field(min_length=1)


class UserGitTokenRequest(BaseModel):
    token: str = Field(min_length=1)


# ═══════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════
def _project_items(
    memory_snapshot: dict, project_id: str
) -> dict[str, list[str]]:
    # Handle both {"banks": {…}} and {bank_id: [items]} formats
    if "banks" in memory_snapshot and isinstance(memory_snapshot["banks"], dict):
        banks = memory_snapshot["banks"]
    else:
        banks = memory_snapshot
    project_banks: dict[str, list[str]] = {}
    for bank_id, items in banks.items():
        matched = [
            item
            for item in items
            if isinstance(item, str) and item.startswith(f"{project_id}:")
        ]
        if matched:
            project_banks[bank_id] = matched
    return project_banks


def _extract_action(artifact: str) -> str:
    for line in artifact.splitlines():
        if line.startswith("- action:"):
            return line.replace("- action:", "", 1).strip()
    return ""


# ── Smart team routing ──────────────────────────────────────────────────────
# Maps each team to the kind of work it does (for keyword-based fallback)
_TEAM_KEYWORDS: dict[str, list[str]] = {
    "product_mgmt":  ["product", "roadmap", "feature", "mvp", "milestone", "vision"],
    "biz_analysis":  ["requirement", "business", "brd", "acceptance", "criteria", "process", "stakeholder"],
    "solution_arch": ["architecture", "design", "system", "diagram", "adr", "component", "integration", "microservice"],
    "api_design":    ["api", "rest", "graphql", "openapi", "endpoint", "contract", "swagger", "grpc"],
    "ux_ui":         ["ui", "ux", "design", "user interface", "wireframe", "flow", "frontend", "screen"],
    "frontend_eng":  ["frontend", "react", "vue", "angular", "html", "css", "javascript", "web", "ui", "component"],
    "backend_eng":   ["backend", "server", "service", "fastapi", "django", "flask", "node", "api", "endpoint", "logic"],
    "database_eng":  ["database", "sql", "postgres", "mysql", "schema", "migration", "table", "query", "orm"],
    "data_eng":      ["data", "pipeline", "etl", "spark", "kafka", "ingestion", "warehouse", "stream"],
    "ml_eng":        ["model", "ml", "machine learning", "ai", "train", "predict", "inference", "dataset"],
    "security_eng":  ["security", "auth", "authentication", "authorization", "vulnerability", "threat", "owasp"],
    "compliance":    ["compliance", "gdpr", "hipaa", "audit", "regulation", "policy", "legal"],
    "devops":        ["deploy", "docker", "kubernetes", "ci/cd", "pipeline", "infrastructure", "cloud", "container"],
    "qa_eng":        ["test", "qa", "quality", "unit test", "integration test", "bug", "validation"],
    "sre_ops":       ["monitoring", "alerting", "slo", "sre", "observability", "incident", "uptime"],
    "docs_team":     ["documentation", "docs", "readme", "guide", "manual", "runbook", "changelog"],
    "feature_eng":   ["feature", "story", "backlog", "sprint", "ticket", "jira", "task"],
}

# Always-on teams for any coding requirement
_CORE_TEAMS = ["solution_arch", "backend_eng", "frontend_eng", "qa_eng", "devops"]

def _select_teams(requirement: str, llm_runtime=None) -> list[str]:
    """Return the ordered subset of teams needed for this requirement.

    1. Try a fast LLM classification call.
    2. Fall back to keyword matching.
    3. Always include _CORE_TEAMS baseline.
    """
    all_teams = list(phase2_pipeline.teams)
    req_lower = requirement.lower()

    # ── LLM selection (best-effort) ──────────────────────────────
    if llm_runtime is not None:
        try:
            team_list = ", ".join(all_teams)
            prompt = (
                f"You are an SDLC orchestrator. Given this requirement:\n\n"
                f"\"{requirement}\"\n\n"
                f"Choose ONLY the teams from this list that genuinely need to contribute. "
                f"Be minimal — skip teams that add no value for this specific requirement. "
                f"Teams: {team_list}\n\n"
                f"Reply with ONLY a comma-separated list of team names, nothing else. "
                f"Example: solution_arch, backend_eng, frontend_eng, qa_eng, devops"
            )
            raw = llm_runtime.generate(
                team="orchestrator",
                requirement=prompt,
                prior_count=0,
                handoff_to="none",
            )
            if raw and raw.content:
                picked = [t.strip() for t in raw.content.replace("\n", ",").split(",") if t.strip() in all_teams]
                if len(picked) >= 2:
                    # Preserve canonical ordering
                    ordered = [t for t in all_teams if t in set(picked)]
                    log.info("LLM selected %d teams for requirement: %s", len(ordered), ordered)
                    return ordered
        except Exception as e:
            log.warning("LLM team selection failed, falling back to keywords: %s", e)

    # ── Keyword fallback ─────────────────────────────────────────
    selected: set[str] = set(_CORE_TEAMS)
    for team, keywords in _TEAM_KEYWORDS.items():
        if any(kw in req_lower for kw in keywords):
            selected.add(team)

    ordered = [t for t in all_teams if t in selected]
    log.info("Keyword-selected %d teams: %s", len(ordered), ordered)
    return ordered


# ═══════════════════════════════════════════════════════════
#  Background pipeline runner (user-scoped persistence)
# ═══════════════════════════════════════════════════════════
def _run_full_pipeline_tracked(
    task_id: str, req: RunRequest, uid: str
) -> None:
    """Execute the pipeline in a background thread.

    Only runs the teams relevant to the requirement (smart routing).
    Persists progress to Firestore, artifacts to GCS or Git.
    """
    teams = _select_teams(req.requirement)
    run_state = {
        "task_id": task_id,
        "project_id": req.project_id,
        "requirement": req.requirement,
        "uid": uid,
        "mode": "full",
        "status": "running",
        "current_team": teams[0] if teams else None,
        "started_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "activities": [
            {"team": t, "status": "pending", "action": "", "artifact_preview": ""}
            for t in teams
        ],
        "result": None,
        "error": None,
    }
    _task_store_save(task_id, run_state, uid, req.project_id)

    # Create user-scoped memory helper
    user_mem = None
    try:
        store = _get_firestore()
        store.upsert_project(uid, req.project_id)

        class _UserMem:
            def recall(self, bank_id, limit=5):
                return store.recall(uid, req.project_id, bank_id, limit)

            def retain(self, bank_id, item):
                store.retain(uid, req.project_id, bank_id, item)

            def snapshot(self):
                return store.memory_snapshot(uid, req.project_id)

        user_mem = _UserMem()
    except Exception:
        log.warning("Firestore unavailable — using shared memory only")

    artifacts: dict[str, str] = {}
    all_code_files: dict[str, dict[str, str]] = {}   # team → {filename: content}
    outputs: list[TaskResult] = []

    # Resolve git config once for all teams
    _git_url = ""
    _git_token = ""
    try:
        git_cfg = _get_firestore().get_git_config(uid, req.project_id)
        if git_cfg and git_cfg.get("git_url"):
            _git_url = git_cfg["git_url"]
            _git_token = _get_firestore().get_git_token(uid) or ""  # user-level PAT
    except Exception:
        pass

    # Resolve Drive folder for Google Docs/Sheets (lazy, best-effort)
    _folder_id = None
    try:
        from factory.tools.google_drive_tool import ensure_project_folder
        _folder_id = ensure_project_folder(req.project_id, uid)
    except Exception as e:
        log.warning("Drive folder setup failed: %s", e)

    try:
        for idx, team in enumerate(teams):
            with task_runs_lock:
                st = task_runs[task_id]
                st["current_team"] = team
                st["activities"][idx]["status"] = "in_progress"
                st["updated_at"] = datetime.now(UTC).isoformat()
            _task_store_save(task_id, run_state, uid, req.project_id)

            bank_id = f"team-{team}"
            prior = (
                user_mem.recall(bank_id, 3) if user_mem
                else memory.recall(bank_id=bank_id, limit=3)
            )

            stage = run_phase2_handler(
                team=team,
                requirement=req.requirement,
                prior_count=len(prior),
                llm_runtime=llm_runtime,
                uid=uid,
                project_id=req.project_id,
                git_url=_git_url,
                git_token=_git_token,
                folder_id=_folder_id,
            )

            artifacts[team] = stage.artifact
            # Collect code files for preview and git push
            if stage.code_files:
                all_code_files[team] = stage.code_files
            summary = (
                f"phase2-stage={team} prior={len(prior)} "
                f"artifact_lines={len(stage.artifact.splitlines())}"
            )
            item = f"{req.project_id}:{summary}:{stage.artifact[:120]}"

            # Persist to user-scoped AND shared memory
            if user_mem:
                user_mem.retain(bank_id, item)
            memory.retain(bank_id=bank_id, item=item)

            outputs.append(
                TaskResult(
                    team=team,
                    objective=req.requirement,
                    status="COMPLETE",
                    reasoning=summary,
                    verified_facts=["phase2-kickoff", f"artifact:{team}"],
                )
            )

            # Build tool usage info for frontend
            tool_entries = []
            for te in getattr(stage, "tools_used", []):
                tool_entries.append({
                    "tool": te.tool,
                    "action": te.action,
                    "success": te.success,
                    "result": {k: v for k, v in (te.result or {}).items() if k in ("doc_url", "sheet_url", "gcs_path", "branch", "preview_url", "files_pushed")},
                })

            with task_runs_lock:
                st = task_runs[task_id]
                st["activities"][idx]["status"] = "complete"
                st["activities"][idx]["action"] = _extract_action(stage.artifact)
                st["activities"][idx]["artifact_preview"] = (
                    stage.artifact[:120].replace("\n", " ")
                )
                st["activities"][idx]["tools_used"] = tool_entries
                st["updated_at"] = datetime.now(UTC).isoformat()
            _task_store_save(task_id, run_state, uid, req.project_id)

        # ── Handoff validation ──
        handoffs: list[dict[str, str | bool]] = []
        for idx, team in enumerate(teams):
            expected = teams[idx + 1] if idx < len(teams) - 1 else "none"
            observed = extract_handoff_to(artifacts.get(team, ""))
            handoffs.append(
                {
                    "team": team,
                    "expected_handoff_to": expected,
                    "observed_handoff_to": observed,
                    "ok": observed == expected,
                }
            )
        overall_handoff_ok = all(bool(x["ok"]) for x in handoffs)

        # ── Persist artifacts (Git or GCS) ──
        storage_info: dict = {"type": "memory_only", "location": ""}
        try:
            git_cfg = _get_firestore().get_git_config(uid, req.project_id)
            if git_cfg and git_cfg.get("git_url"):
                git_token = _get_firestore().get_git_token(uid, req.project_id)
                # Push markdown artifacts (summaries)
                result = _get_git().push_artifacts(
                    git_url=git_cfg["git_url"],
                    git_token=git_token,
                    project_id=req.project_id,
                    task_id=task_id,
                    requirement=req.requirement,
                    artifacts=artifacts,
                )
                storage_info = {"type": "git", **result}
                # Also push code files if any
                if all_code_files:
                    for team_name, team_files in all_code_files.items():
                        try:
                            from factory.tools.git_tool import push_code_files
                            push_code_files(
                                git_url=git_cfg["git_url"],
                                git_token=git_token,
                                project_id=req.project_id,
                                team=team_name,
                                files=team_files,
                            )
                        except Exception as e_code:
                            log.warning("Code file push failed for %s: %s", team_name, e_code)
            else:
                gcs_path = _get_gcs().save_artifacts(
                    uid=uid,
                    project_id=req.project_id,
                    task_id=task_id,
                    requirement=req.requirement,
                    artifacts=artifacts,
                )
                storage_info = {"type": "gcs", "location": gcs_path}
                # Upload code files to GCS too
                if all_code_files and uid:
                    try:
                        from factory.tools.gcs_tool import upload_artifact
                        for team_name, team_files in all_code_files.items():
                            for fname, fcontent in team_files.items():
                                safe_name = fname.replace("/", "_")
                                upload_artifact(uid=uid, project_id=req.project_id, team=team_name, filename=safe_name, content=fcontent)
                    except Exception as e_gcs:
                        log.warning("GCS code upload failed: %s", e_gcs)
        except Exception as e:
            log.warning("Artifact persistence failed: %s", e)
            storage_info = {"type": "memory_only", "error": str(e)}

        run_payload = {
            "project_id": req.project_id,
            "phase": 2,
            "stages": [r.model_dump() for r in outputs],
            "artifacts": artifacts,
            "code_files": all_code_files,  # {team: {filename: content}} — used for live preview
            "handoffs": handoffs,
            "overall_handoff_ok": overall_handoff_ok,
            "governance": llm_runtime.governance_snapshot(),
            "storage": storage_info,
        }

        with task_runs_lock:
            st = task_runs[task_id]
            st["status"] = "completed"
            st["current_team"] = None
            st["result"] = run_payload
            st["updated_at"] = datetime.now(UTC).isoformat()
        _task_store_save(task_id, run_state, uid, req.project_id)

    except Exception as exc:
        with task_runs_lock:
            st = task_runs[task_id]
            st["status"] = "failed"
            st["current_team"] = None
            st["error"] = str(exc)
            st["updated_at"] = datetime.now(UTC).isoformat()
        _task_store_save(task_id, run_state, uid, req.project_id)


# ═══════════════════════════════════════════════════════════
#  PUBLIC (no auth)
# ═══════════════════════════════════════════════════════════
@app.get("/health")
def health() -> dict:
    metrics.inc("ai_factory_health_requests_total")
    return {"status": "ok", "version": "0.2.0", "auth": "firebase"}


@app.get("/metrics", response_class=PlainTextResponse)
def get_metrics() -> PlainTextResponse:
    metrics.inc("ai_factory_metrics_scrapes_total")
    return PlainTextResponse(
        metrics.render_prometheus(), media_type="text/plain; version=0.0.4"
    )


# ═══════════════════════════════════════════════════════════
#  AUTH
# ═══════════════════════════════════════════════════════════
@app.get("/api/auth/me")
def auth_me(user: AuthUser = Depends(get_current_user)) -> dict:
    """Return current user and ensure Firestore profile exists."""
    profile = None
    try:
        profile = _get_firestore().ensure_user(
            user.uid, user.email, user.display_name
        )
    except Exception as e:
        log.warning("Firestore ensure_user failed: %s", e)
    return {
        "uid": user.uid,
        "email": user.email,
        "display_name": user.display_name,
        "profile": profile,
    }


# ═══════════════════════════════════════════════════════════
#  PROJECT MANAGEMENT (user-scoped)
# ═══════════════════════════════════════════════════════════
@app.get("/api/projects")
def list_projects(user: AuthUser = Depends(get_current_user)) -> dict:
    try:
        projects = _get_firestore().list_projects(user.uid)
    except Exception:
        projects = []
    return {"projects": projects}


@app.post("/api/projects")
def create_project(
    body: ProjectCreateRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    pid = body.name.lower().replace(" ", "-").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="Invalid project name")
    project = _get_firestore().upsert_project(
        user.uid, pid, {"name": body.name}
    )
    if body.git_url:
        _get_firestore().save_git_config(
            user.uid, pid, body.git_url, body.git_token or ""
        )
    return project


@app.delete("/api/projects/{project_id}")
def delete_project(
    project_id: str, user: AuthUser = Depends(get_current_user)
) -> dict:
    _get_firestore().delete_project(user.uid, project_id)
    return {"status": "deleted", "project_id": project_id}


# ═══════════════════════════════════════════════════════════
#  GIT CONFIG (per project)
# ═══════════════════════════════════════════════════════════
@app.get("/api/projects/{project_id}/git")
def get_git_config(
    project_id: str, user: AuthUser = Depends(get_current_user)
) -> dict:
    try:
        cfg = _get_firestore().get_git_config(user.uid, project_id)
    except Exception:
        cfg = None
    return cfg or {"git_url": "", "git_token_set": False}


@app.put("/api/projects/{project_id}/git")
def set_git_config(
    project_id: str,
    body: GitConfigRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    _get_firestore().upsert_project(user.uid, project_id)
    _get_firestore().save_git_config(user.uid, project_id, body.git_url)
    return {
        "status": "saved",
        "git_url": body.git_url,
        "git_token_set": _get_firestore().user_git_token_set(user.uid),
    }


@app.delete("/api/projects/{project_id}/git")
def remove_git_config(
    project_id: str, user: AuthUser = Depends(get_current_user)
) -> dict:
    _get_firestore().save_git_config(user.uid, project_id, "", "")
    return {"status": "removed"}


# ═══════════════════════════════════════════════════════════
#  USER GIT TOKEN — stored once, used across all projects
# ═══════════════════════════════════════════════════════════
@app.get("/api/user/git-token")
def get_user_git_token(user: AuthUser = Depends(get_current_user)) -> dict:
    token_set = _get_firestore().user_git_token_set(user.uid)
    return {"token_set": token_set}


@app.put("/api/user/git-token")
def set_user_git_token(
    body: UserGitTokenRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    _get_firestore().save_user_git_token(user.uid, body.token.strip())
    return {"status": "saved", "token_set": True}


@app.delete("/api/user/git-token")
def delete_user_git_token(user: AuthUser = Depends(get_current_user)) -> dict:
    _get_firestore().delete_user_git_token(user.uid)
    return {"status": "removed", "token_set": False}


# ═══════════════════════════════════════════════════════════
#  RUN HISTORY
# ═══════════════════════════════════════════════════════════
@app.get("/api/projects/{project_id}/runs")
def list_runs(
    project_id: str, user: AuthUser = Depends(get_current_user)
) -> dict:
    try:
        runs = _get_firestore().list_runs(user.uid, project_id)
    except Exception:
        runs = []
    return {"runs": runs}


# ═══════════════════════════════════════════════════════════
#  PIPELINE ROUTES (all user-scoped)
# ═══════════════════════════════════════════════════════════
@app.get("/api/settings/tools")
def list_tools(user: AuthUser = Depends(get_current_user)) -> dict:
    return {"tools": tools.list_tools()}


@app.get("/api/team-tools")
def get_team_tools(user: AuthUser = Depends(get_current_user)) -> dict:
    """Return the definitive team → tool mapping for the UI."""
    from factory.tools.team_tools import get_team_tool_summary
    return {"teams": get_team_tool_summary()}


@app.post("/api/pipelines/phase1/run")
def run_phase1(
    req: RunRequest, user: AuthUser = Depends(get_current_user)
) -> dict:
    if not req.project_id.strip() or not req.requirement.strip():
        raise HTTPException(
            status_code=400,
            detail="project_id and requirement are required",
        )
    try:
        _get_firestore().upsert_project(user.uid, req.project_id)
    except Exception:
        pass
    with metrics.track_ms("ai_factory_core_pipeline_duration"):
        run = pipeline.run(
            Phase1Context(
                project_id=req.project_id, requirement=req.requirement
            )
        )
    metrics.inc("ai_factory_core_pipeline_runs_total")
    tracer.event(
        "core.pipeline.run",
        {
            "project_id": req.project_id,
            "stages": len(run.results),
            "status": "completed",
        },
    )
    return {
        "project_id": req.project_id,
        "phase": 1,
        "stages": [r.model_dump() for r in run.results],
        "artifacts": run.artifacts,
    }


@app.post("/api/pipelines/core/run")
def run_core_pipeline(
    req: RunRequest, user: AuthUser = Depends(get_current_user)
) -> dict:
    return run_phase1(req, user)


@app.get("/api/pipelines/phase2/teams")
def phase2_teams(user: AuthUser = Depends(get_current_user)) -> dict:
    return {"phase": 2, "teams": phase2_pipeline.teams}


@app.get("/api/pipelines/full/teams")
def full_pipeline_teams(user: AuthUser = Depends(get_current_user)) -> dict:
    return phase2_teams(user)


@app.post("/api/pipelines/phase2/run")
def run_phase2(
    req: RunRequest, user: AuthUser = Depends(get_current_user)
) -> dict:
    if not req.project_id.strip() or not req.requirement.strip():
        raise HTTPException(
            status_code=400,
            detail="project_id and requirement are required",
        )
    try:
        _get_firestore().upsert_project(user.uid, req.project_id)
    except Exception:
        pass
    with metrics.track_ms("ai_factory_full_pipeline_duration"):
        run = phase2_pipeline.run(
            Phase2Context(
                project_id=req.project_id, requirement=req.requirement
            )
        )
    metrics.inc("ai_factory_full_pipeline_runs_total")
    if run.overall_handoff_ok:
        metrics.inc("ai_factory_full_pipeline_handoff_ok_total")
    else:
        metrics.inc("ai_factory_full_pipeline_handoff_fail_total")
        try:
            delivery = incident_notifier.notify(
                title="AI Factory full pipeline handoff mismatch",
                severity="warning",
                payload={
                    "project_id": req.project_id,
                    "phase": 2,
                    "handoffs": run.handoffs,
                },
            )
            if delivery.get("delivered"):
                metrics.inc("ai_factory_incident_notifications_total")
            else:
                metrics.inc("ai_factory_incident_notifications_skipped_total")
        except Exception:
            metrics.inc("ai_factory_incident_notifications_failed_total")
    tracer.event(
        "full.pipeline.run",
        {
            "project_id": req.project_id,
            "stages": len(run.results),
            "status": "started",
            "handoff_ok": run.overall_handoff_ok,
        },
    )
    return {
        "project_id": req.project_id,
        "phase": 2,
        "stages": [r.model_dump() for r in run.results],
        "artifacts": run.artifacts,
        "handoffs": run.handoffs,
        "overall_handoff_ok": run.overall_handoff_ok,
        "governance": run.governance,
    }


@app.post("/api/pipelines/full/run")
def run_full_pipeline(
    req: RunRequest, user: AuthUser = Depends(get_current_user)
) -> dict:
    return run_phase2(req, user)


@app.post("/api/pipelines/full/run/async")
def run_full_pipeline_async(
    req: RunRequest, user: AuthUser = Depends(get_current_user)
) -> dict:
    if not req.project_id.strip() or not req.requirement.strip():
        raise HTTPException(
            status_code=400,
            detail="project_id and requirement are required",
        )
    try:
        _get_firestore().upsert_project(user.uid, req.project_id)
    except Exception:
        pass
    task_id = f"task-{uuid.uuid4()}"
    worker = threading.Thread(
        target=_run_full_pipeline_tracked,
        args=(task_id, req, user.uid),
        daemon=True,
    )
    worker.start()
    return {"task_id": task_id, "status": "started"}


@app.get("/api/tasks/{task_id}")
def get_task_status(
    task_id: str, user: AuthUser = Depends(get_current_user)
) -> dict:
    task = _task_store_load(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


# ═══════════════════════════════════════════════════════════
#  PROJECT Q&A, CHAT, GROUP CHAT (user-scoped memory)
# ═══════════════════════════════════════════════════════════
@app.post("/api/projects/{project_id}/qa")
def project_qa(
    project_id: str,
    body: ProjectQARequest,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    metrics.inc("ai_factory_project_qa_queries_total")
    try:
        snapshot = {
            "banks": _get_firestore().memory_snapshot(user.uid, project_id)
        }
    except Exception:
        snapshot = {"banks": memory.snapshot()}
    answer, matches = answer_project_question(
        project_id=project_id,
        question=body.question,
        memory_snapshot=snapshot,
    )
    tracer.event(
        "project.qa.query",
        {
            "project_id": project_id,
            "question_length": len(body.question),
            "matches": len(matches),
        },
    )
    return {
        "project_id": project_id,
        "question": body.question,
        "answer": answer,
        "matches": [m.__dict__ for m in matches],
    }


@app.post("/api/projects/{project_id}/ask")
def create_clarification(
    project_id: str,
    body: ClarificationCreateRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    metrics.inc("ai_factory_clarification_requests_total")
    if body.from_team == body.to_team:
        raise HTTPException(
            status_code=400,
            detail="from_team and to_team must be different",
        )
    req = broker.request(
        from_team=body.from_team,
        to_team=body.to_team,
        question=body.question,
    )
    tracer.event(
        "core.clarification.request",
        {
            "project_id": project_id,
            "request_id": req.id,
            "from_team": body.from_team,
            "to_team": body.to_team,
        },
    )
    return {
        "project_id": project_id,
        "request_id": req.id,
        "expires_at": req.expires_at.isoformat(),
    }


@app.post("/api/clarifications/{request_id}/respond")
def respond_clarification(
    request_id: str,
    body: ClarificationRespondRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    metrics.inc("ai_factory_clarification_responses_total")
    broker.respond(request_id=request_id, answer=body.answer)
    tracer.event(
        "core.clarification.respond",
        {"request_id": request_id, "answer_length": len(body.answer)},
    )
    return {"request_id": request_id, "status": "recorded"}


@app.get("/api/clarifications/{request_id}")
def get_clarification(
    request_id: str, user: AuthUser = Depends(get_current_user)
) -> dict:
    return {"request_id": request_id, "answer": broker.get_response(request_id)}


# ═══════════════════════════════════════════════════════════
#  GOVERNANCE (user-scoped settings)
# ═══════════════════════════════════════════════════════════
@app.get("/api/governance/budgets")
def get_budget_governance(
    user: AuthUser = Depends(get_current_user),
) -> dict:
    snapshot = llm_runtime.governance_snapshot()
    # Merge saved user settings if available
    try:
        saved = _get_firestore().get_team_settings(user.uid, "default")
        if saved:
            for team_key, overrides in saved.items():
                if team_key in snapshot.get("teams", {}):
                    snapshot["teams"][team_key].update(overrides)
    except Exception:
        pass
    return snapshot


@app.put("/api/governance/teams/{team}")
def update_team_governance(
    team: str,
    body: TeamConfigUpdateRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    if body.model is None and body.budget_usd is None and body.api_key is None:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one setting: model, budget_usd, or api_key",
        )
    try:
        updated = llm_runtime.update_team_config(
            team=team,
            model=body.model,
            budget_usd=body.budget_usd,
            api_key=body.api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Persist to Firestore
    try:
        _get_firestore().save_team_settings(
            user.uid,
            "default",
            {team: {"model": updated.get("model"), "limit_usd": updated.get("limit_usd")}},
        )
    except Exception:
        pass
    return {"status": "updated", **updated}


# ═══════════════════════════════════════════════════════════
#  MEMORY MAP (user-scoped)
# ═══════════════════════════════════════════════════════════
@app.get("/api/projects/{project_id}/memory-map")
def project_memory_map(
    project_id: str, user: AuthUser = Depends(get_current_user)
) -> dict:
    try:
        snapshot = _get_firestore().memory_snapshot(user.uid, project_id)
    except Exception:
        snapshot = memory.snapshot()
    project_banks = _project_items(snapshot, project_id)

    nodes: list[dict] = []
    edges: list[dict] = []
    team_to_items: dict[str, int] = defaultdict(int)

    for bank_id, items in project_banks.items():
        team = bank_id.replace("team-", "")
        team_to_items[team] += len(items)
        nodes.append(
            {"id": bank_id, "type": "memory_bank", "team": team, "items": len(items)}
        )

    if not nodes:
        return {
            "project_id": project_id,
            "nodes": [],
            "edges": [],
            "summary": {"banks": 0, "items": 0},
        }

    if len(nodes) > 1:
        for idx in range(len(nodes) - 1):
            edges.append(
                {
                    "from": str(nodes[idx]["id"]),
                    "to": str(nodes[idx + 1]["id"]),
                    "label": "context_flow",
                }
            )

    return {
        "project_id": project_id,
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "banks": len(nodes),
            "items": sum(team_to_items.values()),
        },
    }


# ═══════════════════════════════════════════════════════════
#  PROJECT CHAT (user-scoped memory)
# ═══════════════════════════════════════════════════════════
@app.post("/api/projects/{project_id}/chat")
def project_chat(
    project_id: str,
    body: ProjectChatRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    try:
        snapshot = {
            "banks": _get_firestore().memory_snapshot(user.uid, project_id)
        }
    except Exception:
        snapshot = {"banks": memory.snapshot()}
    answer, matches = answer_project_question(
        project_id=project_id,
        question=body.message,
        memory_snapshot=snapshot,
    )
    # Save chat turns to user-scoped memory
    bank_id = f"project-chat-{project_id}"
    try:
        store = _get_firestore()
        store.retain(user.uid, project_id, bank_id, f"{project_id}:user:{body.message}")
        store.retain(user.uid, project_id, bank_id, f"{project_id}:assistant:{answer}")
    except Exception:
        memory.retain(bank_id=bank_id, item=f"{project_id}:user:{body.message}")
        memory.retain(bank_id=bank_id, item=f"{project_id}:assistant:{answer}")
    return {
        "project_id": project_id,
        "message": body.message,
        "answer": answer,
        "matches": [m.__dict__ for m in matches],
    }


# ═══════════════════════════════════════════════════════════
#  GROUP CHAT
# ═══════════════════════════════════════════════════════════
@app.post("/api/projects/{project_id}/group-chat")
def project_group_chat(
    project_id: str,
    body: GroupChatRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    participants = body.participants or phase2_pipeline.teams[:5]
    mem_map = project_memory_map(project_id, user)

    plan: list[str]
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                f"{groupchat_service_url}/session/plan",
                json={"topic": body.topic, "participants": participants},
            )
            resp.raise_for_status()
            plan = list(resp.json().get("plan", []))
    except Exception:
        plan = [
            "align-on-goal",
            "split-by-team",
            "collect-findings",
            "decide-next-actions",
        ]

    updates = []
    for p in participants:
        team_bank = f"team-{p}"
        node = next(
            (n for n in mem_map["nodes"] if n.get("id") == team_bank), None
        )
        item_count = int(node.get("items", 0)) if isinstance(node, dict) else 0
        updates.append(
            {"team": p, "status": f"context_items={item_count}", "topic": body.topic}
        )

    return {
        "project_id": project_id,
        "topic": body.topic,
        "participants": participants,
        "plan": plan,
        "updates": updates,
    }


@app.get("/api/observability/incidents/config")
def get_incident_config(
    user: AuthUser = Depends(get_current_user),
) -> dict:
    return incident_notifier.config_snapshot()
