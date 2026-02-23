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
import asyncio
import json
import threading
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse, PlainTextResponse, StreamingResponse

from factory.auth.firebase_auth import AuthUser, get_current_user
from factory.clarification.broker import ClarificationBroker
from factory.agents.phase2_handlers import extract_handoff_to, run_phase2_handler
from factory.agents.task_result import TaskResult
from factory.llm.runtime import TeamLLMRuntime
from factory.memory.decision_log import DecisionLog, TEAM_DECISION_TYPE
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
hitl_service_url = os.getenv("HITL_SERVICE_URL", "http://hitl:8007")

# Teams list for knowledge sharing
ALL_TEAMS = list(phase2_pipeline.teams)

# @mention routing helpers — shared with frontend via TEAM_ALIASES map
from factory.groupchat.mentions import TEAM_ALIASES, parse_mentions as _parse_mentions

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
#  Self-Heal infrastructure
# ═══════════════════════════════════════════════════════════
# Circular error buffer — keyed by project_id
_error_buffer: dict[str, deque] = defaultdict(lambda: deque(maxlen=50))
_error_buffer_lock = threading.Lock()

# Active watchdog stop-events — keyed by "{uid}:{project_id}"
_watchers: dict[str, threading.Event] = {}
_watchers_lock = threading.Lock()

# Heal history — keyed by project_id (last 50 entries)
_heal_history: dict[str, list] = defaultdict(list)
_heal_history_lock = threading.Lock()

# Lazy SelfHealAgent
_self_heal_agent = None


def _get_self_heal_agent():
    global _self_heal_agent
    if _self_heal_agent is None:
        from factory.agents.self_heal import SelfHealAgent
        _self_heal_agent = SelfHealAgent(llm_runtime=llm_runtime)
    return _self_heal_agent


def _push_error(project_id: str, level: str, msg: str) -> None:
    """Append an error entry to the project error buffer."""
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "level": level,
        "msg": msg[:500],
        "project_id": project_id,
    }
    with _error_buffer_lock:
        _error_buffer[project_id].append(entry)


# ═══════════════════════════════════════════════════════════
#  In-memory task tracker (real-time polling) + Firestore sync
# ═══════════════════════════════════════════════════════════
task_runs: dict[str, dict] = {}
task_runs_lock = threading.Lock()

# Per-task communications log — keyed by task_id
# Each entry: {ts, type, from_team, to_team, message}
_comms_logs: dict[str, list] = defaultdict(list)
_comms_logs_lock = threading.Lock()


def _push_comms(task_id: str, from_team: str, to_team: str, msg_type: str, message: str) -> None:
    """Append a team-to-team communication event to the task comms log."""
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "type": msg_type,        # "handoff" | "context" | "clarification" | "status"
        "from_team": from_team,
        "to_team": to_team,
        "message": message[:600],
    }
    with _comms_logs_lock:
        _comms_logs[task_id].append(entry)


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
    existing_code: dict | None = None   # {team: {filename: content}} from a prior run
    is_followup: bool = False


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
    topic: str = Field(min_length=1)
    participants: list[str] = Field(default_factory=list)
    max_turns: int = Field(default=1, ge=1, le=3)


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    git_url: str | None = None
    git_token: str | None = None


class GitConfigRequest(BaseModel):
    git_url: str = Field(min_length=5)


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
    teams = _select_teams(req.requirement, llm_runtime)
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
    qa_verdict: str = "N/A"
    qa_issues: list[str] = []

    # Decision log for this run
    try:
        _dec_log: DecisionLog | None = DecisionLog(store=_get_firestore())
    except Exception:
        _dec_log = None

    # ── Pre-populate all_code_files with existing code so new output EXTENDS it ──
    prior_code: dict[str, dict[str, str]] = {}
    if req.existing_code and req.is_followup:
        for team_name, team_files in req.existing_code.items():
            if team_files:
                prior_code[team_name] = dict(team_files)
                all_code_files[team_name] = dict(team_files)  # start with existing

    # Build context string for the LLM so it knows what already exists
    existing_code_ctx = ""
    if prior_code:
        parts = []
        for team_name, team_files in prior_code.items():
            for fname, fcontent in team_files.items():
                truncated = fcontent[:1200] + ("\n... (truncated)" if len(fcontent) > 1200 else "")
                parts.append(f"### {team_name}/{fname}\n{truncated}")
        if parts:
            existing_code_ctx = (
                "\n\n=== EXISTING PROJECT CODE (modify/extend this, do NOT rewrite from scratch) ==="
                "\n⚠️ IMPORTANT: You MUST preserve all existing functionality. Only ADD or MODIFY the specific part requested."
                "\n" + "\n\n".join(parts[:12])
                + "\n=== END EXISTING CODE ==="
            )
    effective_req = req.requirement + existing_code_ctx

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

    # ── Inter-team knowledge accumulation ──────────────────────────────────────
    # These teams produce architectural decisions, requirements, or design
    # rationale that all downstream teams should build on top of.
    _KNOWLEDGE_PRODUCERS_SET = frozenset({
        "product_mgmt", "biz_analysis", "solution_arch",
        "api_design", "ux_ui", "security_eng",
        "backend_eng", "database_eng", "frontend_eng", "devops", "qa_eng",
    })
    shared_knowledge_parts: list[str] = []

    # Announce pipeline start in comms log
    _push_comms(task_id, "orchestrator", teams[0] if teams else "none", "status",
                f"Pipeline started for: {req.requirement[:200]}. Selected teams: {', '.join(teams)}")

    try:
        for idx, team in enumerate(teams):
            with task_runs_lock:
                st = task_runs[task_id]
                st["current_team"] = team
                st["activities"][idx]["status"] = "in_progress"
                st["updated_at"] = datetime.now(UTC).isoformat()
            _task_store_save(task_id, run_state, uid, req.project_id)

            # Announce team starting
            _push_comms(task_id, "orchestrator", team, "status",
                        f"Assigning task to {team}. Shared context from {len(shared_knowledge_parts)} upstream team(s).")

            bank_id = f"team-{team}"
            prior = (
                user_mem.recall(bank_id, 3) if user_mem
                else memory.recall(bank_id=bank_id, limit=3)
            )

            # Build flat code map for QA validation
            flat_code = {}
            if team == "qa_eng":
                for _t, _files in all_code_files.items():
                    for _fname, _content in _files.items():
                        flat_code[_fname] = _content

            stage = run_phase2_handler(
                team=team,
                requirement=effective_req,
                prior_count=len(prior),
                llm_runtime=llm_runtime,
                uid=uid,
                project_id=req.project_id,
                git_url=_git_url,
                git_token=_git_token,
                folder_id=_folder_id,
                all_code=flat_code or None,
                shared_knowledge="\n\n".join(shared_knowledge_parts),
                next_team=teams[idx + 1] if idx + 1 < len(teams) else "none",
            )

            artifacts[team] = stage.artifact
            # Collect code files for preview and git push — MERGE with prior, don't replace
            if stage.code_files:
                if team not in all_code_files:
                    all_code_files[team] = {}
                all_code_files[team].update(stage.code_files)  # new files override, old files kept

            # Capture QA validation results
            if team == "qa_eng" and stage.qa_verdict:
                qa_verdict = stage.qa_verdict
                qa_issues = list(stage.qa_issues)

            # ── Log team decision to Firestore ──────────────────────────────
            if _dec_log is not None:
                try:
                    _dec_log.record(
                        uid=uid,
                        project_id=req.project_id,
                        team=team,
                        decision_type=stage.decision_type,
                        title=stage.decision_title,
                        rationale=stage.decision_rationale,
                        artifact_ref=f"memory://team-{team}",
                    )
                except Exception as _dec_exc:
                    log.warning("Decision log failed for %s: %s", team, _dec_exc)

            # ── Harvest knowledge for downstream teams ───────────────────────
            # Key producers' rationale/decisions are accumulated so that every
            # team that runs AFTER them automatically receives this as context.
            if team in _KNOWLEDGE_PRODUCERS_SET:
                _rationale = stage.decision_rationale or ""
                _title = stage.decision_title or team
                if _rationale:
                    _label = team.replace("_", " ").title()
                    # Sol Arch gets more space as it's foundational; others get 800 chars
                    _max_chars = 1200 if team == "solution_arch" else 800
                    shared_knowledge_parts.append(
                        f"[{_label}] {_title}:\n{_rationale[:_max_chars]}"
                    )
                    # Emit context-share comms event to downstream teams
                    next_team = teams[idx + 1] if idx + 1 < len(teams) else "all"
                    _push_comms(task_id, team, next_team, "context",
                                f"{_title}: {_rationale[:300]}")

            # ── Emit handoff comms event ──────────────────────────────────
            _action = _extract_action(stage.artifact)
            next_team = teams[idx + 1] if idx + 1 < len(teams) else "none"
            _push_comms(task_id, team, next_team, "handoff",
                        f"{_action or 'Completed work'} → passing to {next_team}. "
                        f"Artifact: {stage.artifact[:200].replace(chr(10), ' ')}")

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

        # ── Build unified project structure ──
        # Merge all team code into one flat file tree, keeping team attribution
        unified_code: dict[str, str] = {}        # fname → content
        file_attribution: dict[str, str] = {}    # fname → team
        for team_name, team_files in all_code_files.items():
            for fname, content in team_files.items():
                unified_code[fname] = content
                file_attribution[fname] = team_name

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
                # Push unified code as a single branch (not per-team)
                if unified_code:
                    try:
                        from factory.tools.git_tool import push_files
                        push_result = push_files(
                            git_url=git_cfg["git_url"],
                            git_token=git_token,
                            project_id=req.project_id,
                            branch_suffix=f"task-{task_id[:8]}",
                            files=unified_code,
                            commit_message=f"AI Factory: {req.requirement[:80]}",
                        )
                        storage_info["code_branch"] = push_result.get("branch", "")
                        storage_info["files_pushed"] = push_result.get("files_pushed", 0)
                    except Exception as e_code:
                        log.warning("Unified code push failed: %s", e_code)
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
                if unified_code and uid:
                    try:
                        from factory.tools.gcs_tool import upload_artifact
                        for fname, fcontent in unified_code.items():
                            safe_name = fname.replace("/", "_")
                            upload_artifact(uid=uid, project_id=req.project_id, team="unified", filename=safe_name, content=fcontent)
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
            "code_files": all_code_files,  # {team: {filename: content}} — kept for attribution
            "unified_code": unified_code,  # {filename: content} — flat project tree
            "file_attribution": file_attribution,  # {filename: team}
            "handoffs": handoffs,
            "overall_handoff_ok": overall_handoff_ok,
            "qa_verdict": qa_verdict,
            "qa_issues": qa_issues,
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

        # ── Auto-merge all AI branches into main after successful run ──────────
        try:
            git_cfg2 = _get_firestore().get_git_config(uid, req.project_id)
            if git_cfg2 and git_cfg2.get("git_url"):
                git_token2 = _get_firestore().get_git_token(uid) or ""
                if git_token2:
                    merge_summary = _get_git().merge_all_ai_branches(
                        git_url=git_cfg2["git_url"],
                        git_token=git_token2,
                        target_branch="main",
                    )
                    log.info("Auto-merge after pipeline: %s", merge_summary)
                    with task_runs_lock:
                        task_runs[task_id]["result"]["auto_merge"] = merge_summary
        except Exception as _am_exc:
            log.warning("Auto-merge failed (non-fatal): %s", _am_exc)

    except Exception as exc:
        _push_error(req.project_id, "ERROR", f"Pipeline task {task_id} failed: {exc}")
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


@app.get("/api/tasks/{task_id}/stream")
async def stream_task_status(
    task_id: str, user: AuthUser = Depends(get_current_user)
) -> StreamingResponse:
    """SSE endpoint — pushes task state updates as server-sent events.

    The client receives a ``data: <json>`` line each time the task status or
    active team changes, followed by a ``event: done`` when the task finishes.
    """
    async def _event_generator():
        last_status: str | None = None
        last_team: str | None = None
        # Max 5 minutes at 0.5 s polling = 600 iterations
        for _ in range(600):
            task = _task_store_load(task_id)
            if task is None:
                yield f"event: error\ndata: {json.dumps({'detail': 'task not found'})}\n\n"
                return

            current_status = task.get("status")
            current_team = task.get("current_team")

            # Emit on first call or whenever something changes
            if current_status != last_status or current_team != last_team:
                yield f"data: {json.dumps(task)}\n\n"
                last_status = current_status
                last_team = current_team

            if current_status in ("completed", "failed"):
                yield (
                    f"event: done\n"
                    f"data: {json.dumps({'task_id': task_id, 'status': current_status})}\n\n"
                )
                return

            await asyncio.sleep(0.5)

        # Timeout — tell client to fall back to polling
        yield f"event: timeout\ndata: {json.dumps({'task_id': task_id})}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/tasks/{task_id}/comms")
def get_task_comms(
    task_id: str,
    since: int = 0,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Return the inter-team communications log for a running or completed task.

    ``since`` is an optional index offset — pass the number of events already
    received to get only new events (supports incremental polling).
    """
    with _comms_logs_lock:
        all_events = list(_comms_logs.get(task_id, []))
    task = _task_store_load(task_id)
    return {
        "task_id": task_id,
        "total": len(all_events),
        "events": all_events[since:],
        "task_status": task.get("status") if task else "unknown",
    }



@app.post("/api/projects/{project_id}/qa")
def project_qa(
    project_id: str,
    body: ProjectQARequest,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    metrics.inc("ai_factory_project_qa_queries_total")
    try:
        snapshot = _get_firestore().memory_snapshot(user.uid, project_id)
    except Exception:
        snapshot = memory.snapshot()
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
#  HITL (Human-in-the-Loop) — proxy to hitl_svc
# ═══════════════════════════════════════════════════════════

class HITLSubmitRequest(BaseModel):
    team: str = Field(min_length=2)
    question: str = Field(min_length=5)
    context: str = ""
    urgency: str = "normal"
    options: list[str] = Field(default_factory=list)


class HITLRespondRequest(BaseModel):
    decision: str = Field(min_length=1)
    comment: str = ""


@app.post("/api/projects/{project_id}/hitl/requests", status_code=201)
def submit_hitl_request(
    project_id: str,
    body: HITLSubmitRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Submit a new HITL escalation request to the HITL service."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                f"{hitl_service_url}/hitl/requests",
                json={
                    "project_id": project_id,
                    "task_id": None,
                    "team": body.team,
                    "question": body.question,
                    "context": body.context,
                    "urgency": body.urgency,
                    "options": body.options,
                },
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"HITL service unavailable: {exc}")


@app.get("/api/projects/{project_id}/hitl/pending")
def get_hitl_pending(
    project_id: str,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Return pending HITL escalation requests for a project."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(
                f"{hitl_service_url}/hitl/pending",
                params={"project_id": project_id},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"HITL service unavailable: {exc}")


@app.post("/api/hitl/requests/{request_id}/respond")
def respond_hitl_request(
    request_id: str,
    body: HITLRespondRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Human operator submits a decision for a pending HITL request."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                f"{hitl_service_url}/hitl/requests/{request_id}/respond",
                json={"decision": body.decision, "comment": body.comment},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"HITL service unavailable: {exc}")


@app.get("/api/hitl/requests/{request_id}")
def get_hitl_request(
    request_id: str,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Poll the status of a HITL escalation request."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{hitl_service_url}/hitl/requests/{request_id}")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"HITL service unavailable: {exc}")


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
#  DECISIONS — team decision log (ADRs, acceptance criteria, etc.)
# ═══════════════════════════════════════════════════════════
@app.get("/api/projects/{project_id}/decisions")
def get_project_decisions(
    project_id: str,
    team: str | None = None,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Return decision entries for a project, optionally filtered by ?team=<name>.

    Used by the frontend Memory Map to show structured decisions on node click.
    """
    try:
        decisions = DecisionLog(store=_get_firestore()).list(
            uid=user.uid,
            project_id=project_id,
            team=team,
            limit=100,
        )
    except Exception as exc:
        log.warning("Failed to load decisions for %s: %s", project_id, exc)
        decisions = []
    return {
        "project_id": project_id,
        "team": team,
        "total": len(decisions),
        "decisions": decisions,
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
        snapshot = _get_firestore().memory_snapshot(user.uid, project_id)
    except Exception:
        snapshot = memory.snapshot()
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
#  SESSION RESTORE
# ═══════════════════════════════════════════════════════════
@app.get("/api/projects/{project_id}/session")
def get_project_session(
    project_id: str,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Return last pipeline run + chat history so the frontend can restore on reload."""
    result: dict = {"chat_history": [], "last_run": None, "last_task_id": None}
    try:
        store = _get_firestore()
        # ── Chat history ──────────────────────────────────────────
        bank_id = f"project-chat-{project_id}"
        try:
            raw_items = store.recall(user.uid, project_id, bank_id, limit=60)
        except Exception:
            raw_items = []
        for item in raw_items:
            u_tag = f"{project_id}:user:"
            a_tag = f"{project_id}:assistant:"
            if u_tag in item:
                result["chat_history"].append({"role": "user", "text": item.split(u_tag, 1)[1]})
            elif a_tag in item:
                result["chat_history"].append({"role": "assistant", "text": item.split(a_tag, 1)[1]})
        # ── Last pipeline run ──────────────────────────────────────
        try:
            runs = store.list_runs(user.uid, project_id, limit=1)
            if runs:
                latest = runs[0]
                result["last_task_id"] = latest.get("task_id") or latest.get("id")
                result["last_run"] = latest
        except Exception:
            pass
    except Exception as exc:
        log.warning("Session restore failed for project %s: %s", project_id, exc)
    return result


# ═══════════════════════════════════════════════════════════
#  GROUP CHAT — A2A multi-agent discussion
# ═══════════════════════════════════════════════════════════
@app.post("/api/projects/{project_id}/group-chat")
def project_group_chat(
    project_id: str,
    body: GroupChatRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    # ── @mention routing: if topic contains @tags, only those teams respond ──
    mentioned = _parse_mentions(body.topic)
    if mentioned:
        participants = mentioned
    else:
        participants = body.participants or phase2_pipeline.teams[:5]

    # ── Build rich per-team context from persisted memory ─────────────────
    # Fetch up to 10 memory items per team (500 chars each) so reopened
    # projects have full context about their prior work on this project.
    team_contexts: dict[str, str] = {}
    try:
        snapshot = _get_firestore().memory_snapshot(user.uid, project_id)
    except Exception:
        snapshot = memory.snapshot()
    for p in participants:
        bank_items = snapshot.get(f"team-{p}", [])
        relevant = [
            i for i in bank_items
            if isinstance(i, str) and i.startswith(f"{project_id}:")
        ][:10]
        if relevant:
            team_contexts[p] = "\n".join(r.split(":", 1)[-1][:500] for r in relevant)

    # Last pipeline requirement gives shared context about what was built
    last_requirement = ""
    try:
        runs = _get_firestore().list_runs(user.uid, project_id, limit=1)
        if runs:
            last_requirement = runs[0].get("requirement", "")[:400]
    except Exception:
        pass

    full_context = (
        (f"Last pipeline requirement: {last_requirement}\n\n" if last_requirement else "")
        + "\n".join(
            f"[{p}] Prior work:\n{team_contexts[p]}"
            for p in participants if p in team_contexts
        )
    )

    # ── Try the dedicated groupchat service (proper multi-turn A2A) ────────
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{groupchat_service_url}/session/discuss",
                json={
                    "topic": body.topic,
                    "participants": participants,
                    "max_turns": body.max_turns,
                    "context": full_context,
                },
            )
            resp.raise_for_status()
            gc = resp.json()
            for d in gc.get("discussion", []):
                d.setdefault("message", d.get("summary", ""))
            return {
                "project_id": project_id,
                "topic": body.topic,
                "participants": participants,
                "tagged_teams": mentioned,
                **gc,
            }
    except Exception as _gc_exc:
        log.warning("Groupchat service unavailable — using inline A2A LLM: %s", _gc_exc)

    # ── Fallback: inline A2A LLM with full prior-turn + per-team context ──
    plan = ["align-on-goal", "split-by-team", "collect-findings", "decide-next-actions"]
    discussion: list[dict] = []

    for _turn in range(max(1, body.max_turns)):
        for p in participants:
            prior_lines = "\n".join(
                f"  {d['team'].replace('_',' ')}: {d['message'][:250]}"
                for d in discussion[-6:]
            )
            team_mem = team_contexts.get(p, "")
            prompt = (
                f"You are the {p.replace('_', ' ')} team lead answering on project '{project_id}'.\n"
                + (f"Topic / question: {body.topic}\n" if not mentioned
                   else f"You were directly asked (@{p}): {body.topic}\n")
                + (f"\nYour prior work on this project:\n{team_mem[:800]}\n" if team_mem else "")
                + (f"\nProject context:\n{full_context[:400]}\n" if full_context else "")
                + (
                    f"\nDiscussion so far:\n{prior_lines}\n\n"
                    if prior_lines else "\nYou are the first to speak.\n\n"
                )
                + "Respond in 2-4 sentences. Be direct, technical, and reference your project work."
            )
            try:
                result = llm_runtime.generate(team=p, requirement=prompt, prior_count=0, handoff_to="none")
                content = (result.content.strip() if result and result.content
                           else f"[{p.replace('_',' ')}] Reviewing '{body.topic}' — will align with team.")
                source = result.source if result else "fallback"
            except Exception:
                content = f"[{p.replace('_',' ')}] Reviewing '{body.topic}' — will align with team."
                source = "fallback"
            discussion.append({
                "round": _turn + 1,
                "team": p,
                "message": content,
                "source": source,
            })

    # ── Consensus synthesis via solution_arch ─────────────────────────────
    consensus = f"Teams reached consensus on: {body.topic}"
    action_items: list[str] = []
    if llm_runtime.enabled:
        try:
            transcript = "\n".join(f"{d['team'].replace('_',' ')}: {d['message'][:200]}" for d in discussion)
            synth_prompt = (
                f"Summarise this multi-team engineering discussion.\n\n"
                f"Topic: {body.topic}\n\nTranscript:\n{transcript}\n\n"
                f"Reply in EXACTLY this format:\n"
                f"CONSENSUS: <one sentence>\n"
                f"ACTION_1: <action item>\nACTION_2: <action item>\nACTION_3: <action item>\n"
            )
            synth = llm_runtime.generate(team="solution_arch", requirement=synth_prompt, prior_count=0, handoff_to="none")
            if synth and synth.content:
                for line in synth.content.splitlines():
                    if line.startswith("CONSENSUS:"):
                        consensus = line.split(":", 1)[1].strip()
                    elif line.startswith("ACTION_"):
                        item = line.split(":", 1)[1].strip()
                        if item:
                            action_items.append(item)
        except Exception:
            pass
    if not action_items:
        action_items = [
            f"Implement the agreed solution for: {body.topic}",
            "Schedule follow-up review in 48 hours",
            "Update project documentation with decisions",
        ]

    return {
        "project_id": project_id,
        "topic": body.topic,
        "participants": participants,
        "tagged_teams": mentioned,
        "plan": plan,
        "discussion": discussion,
        "consensus": consensus,
        "action_items": action_items,
    }


@app.get("/api/observability/incidents/config")
def get_incident_config(
    user: AuthUser = Depends(get_current_user),
) -> dict:
    return incident_notifier.config_snapshot()


# ═══════════════════════════════════════════════════════════
#  MERGE TEAM  — Git branch listing + merge via GitHub API
# ═══════════════════════════════════════════════════════════
class MergeRequest(BaseModel):
    source_branch: str
    target_branch: str = "main"


class GitLearnRequest(BaseModel):
    branch: str = "main"


@app.get("/api/projects/{project_id}/git/branches")
def list_git_branches(
    project_id: str,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """List repository branches with metadata."""
    try:
        git_cfg = _get_firestore().get_git_config(user.uid, project_id)
        if not (git_cfg and git_cfg.get("git_url")):
            return {"branches": [], "error": "No git repository configured for this project"}
        git_token = _get_firestore().get_git_token(user.uid) or ""
        if not git_token:
            return {"branches": [], "error": "No GitHub PAT configured — go to Settings → GitHub Token"}
        branches = _get_git().list_branches(git_cfg["git_url"], git_token)
        return {"branches": branches, "git_url": git_cfg["git_url"]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/git/merge")
def merge_git_branch(
    project_id: str,
    body: MergeRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Merge source_branch into target_branch via GitHub API."""
    try:
        git_cfg = _get_firestore().get_git_config(user.uid, project_id)
        if not (git_cfg and git_cfg.get("git_url")):
            raise HTTPException(status_code=400, detail="No git repository configured")
        git_token = _get_firestore().get_git_token(user.uid) or ""
        if not git_token:
            raise HTTPException(status_code=400, detail="No GitHub PAT configured")
        result = _get_git().merge_branch(
            git_url=git_cfg["git_url"],
            git_token=git_token,
            source_branch=body.source_branch,
            target_branch=body.target_branch,
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/git/merge-all")
def merge_all_git_branches(
    project_id: str,
    user: AuthUser = Depends(get_current_user),
    target: str = "main",
) -> dict:
    """Merge every ai-factory/* branch into target (default: main)."""
    try:
        git_cfg = _get_firestore().get_git_config(user.uid, project_id)
        if not (git_cfg and git_cfg.get("git_url")):
            raise HTTPException(status_code=400, detail="No git repository configured")
        git_token = _get_firestore().get_git_token(user.uid) or ""
        if not git_token:
            raise HTTPException(status_code=400, detail="No GitHub PAT configured")
        result = _get_git().merge_all_ai_branches(
            git_url=git_cfg["git_url"],
            git_token=git_token,
            target_branch=target,
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/git/files")
def get_git_repo_files(
    project_id: str,
    branch: str = "main",
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Fetch all code files from the repo for display in Live Preview."""
    try:
        git_cfg = _get_firestore().get_git_config(user.uid, project_id)
        if not (git_cfg and git_cfg.get("git_url")):
            return {"files": {}, "file_list": [], "error": "No git repository configured"}
        git_token = _get_firestore().get_git_token(user.uid) or ""
        if not git_token:
            return {"files": {}, "file_list": [], "error": "No GitHub PAT configured"}
        raw = _get_git().fetch_repo_tree(git_cfg["git_url"], git_token, branch, max_files=120)
        files = {}
        for f in raw:
            if f["content"] and not f["content"].startswith("("):
                files[f["path"]] = f["content"]
        return {
            "files": files,
            "file_list": [{"path": f["path"], "size": f["size"]} for f in raw],
            "branch": branch,
            "git_url": git_cfg["git_url"],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ═══════════════════════════════════════════════════════════
#  GIT LEARN — fetch repo, learn as solution_arch, share knowledge
# ═══════════════════════════════════════════════════════════
@app.post("/api/projects/{project_id}/git/learn")
def learn_git_repo(
    project_id: str,
    body: GitLearnRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Fetch repo contents, have solution_arch learn it, store knowledge for all agents."""
    git_cfg = _get_firestore().get_git_config(user.uid, project_id)
    if not (git_cfg and git_cfg.get("git_url")):
        raise HTTPException(status_code=400, detail="No git repository configured")
    git_token = _get_firestore().get_git_token(user.uid) or ""
    if not git_token:
        raise HTTPException(status_code=400, detail="No GitHub PAT")

    files = _get_git().fetch_repo_tree(git_cfg["git_url"], git_token, body.branch)
    if not files or (len(files) == 1 and files[0]["path"] == "error"):
        return {"status": "failed", "error": files[0]["content"] if files else "empty"}

    # Build a summary of the repo structure
    tree_summary = "\n".join(f"  {f['path']} ({f['size']}B)" for f in files[:80])
    key_contents = "\n\n".join(
        f"### {f['path']}\n{f['content'][:2000]}"
        for f in files
        if f['content'] and not f['content'].startswith('(')
    )[:12000]

    # Have LLM (solution_arch) analyze and take notes
    analysis_prompt = (
        f"You are the Solution Architect studying an existing codebase for project '{project_id}'.\n"
        f"Analyze the repository and produce structured notes that all team agents can reference.\n\n"
        f"REPO STRUCTURE:\n{tree_summary}\n\n"
        f"KEY FILES:\n{key_contents}\n\n"
        f"Produce notes covering:\n"
        f"1. TECH STACK: languages, frameworks, libraries\n"
        f"2. ARCHITECTURE: patterns, folder structure, entry points\n"
        f"3. KEY COMPONENTS: main modules, their purposes\n"
        f"4. DATA MODEL: schemas, models, database\n"
        f"5. API SURFACE: endpoints, routes\n"
        f"6. BUILD & DEPLOY: scripts, configs, CI/CD\n"
        f"7. CONVENTIONS: naming, style, patterns to follow\n"
    )
    notes = ""
    try:
        result = llm_runtime.generate(team="solution_arch", requirement=analysis_prompt, prior_count=0, handoff_to="none")
        if result and result.content:
            notes = result.content
    except Exception:
        notes = f"Tech stack analysis:\nFiles: {len(files)}\nStructure:\n{tree_summary[:3000]}"

    # Store in memory for ALL teams
    store = _get_firestore()
    repo_knowledge = f"{project_id}:repo_knowledge:{notes[:4000]}"
    for team in ALL_TEAMS:
        bank_id = f"team-{team}"
        try:
            store.retain(user.uid, project_id, bank_id, repo_knowledge)
        except Exception:
            pass
    # Also store file index
    file_index = f"{project_id}:repo_files:" + ", ".join(f['path'] for f in files[:100])
    try:
        store.retain(user.uid, project_id, "team-solution_arch", file_index)
    except Exception:
        pass

    return {
        "status": "learned",
        "files_analyzed": len(files),
        "notes_length": len(notes),
        "notes_preview": notes[:500],
        "file_tree": [f["path"] for f in files[:60]],
    }


class GitCloneRequest(BaseModel):
    clone_url: str = Field(min_length=5, description="URL of the external repo to clone and learn from")
    branch: str = "main"


@app.post("/api/projects/{project_id}/git/clone")
def clone_external_repo(
    project_id: str,
    body: GitCloneRequest,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Clone an external repository, analyze its codebase, and store the knowledge
    so all pipeline agents can build on top of it.

    This enables the 'build on top of existing repo' workflow: paste any public
    (or private, if token is set) repo URL and the agents will learn its structure,
    tech stack, and conventions before running the pipeline.
    """
    git_token = ""
    try:
        git_token = _get_firestore().get_git_token(user.uid) or ""
    except Exception:
        pass

    files = _get_git().fetch_repo_tree(body.clone_url, git_token, body.branch, max_files=120)
    if not files or (len(files) == 1 and files[0]["path"] == "error"):
        return {"status": "failed", "error": files[0]["content"] if files else "empty"}

    tree_summary = "\n".join(f"  {f['path']} ({f['size']}B)" for f in files[:100])
    key_contents = "\n\n".join(
        f"### {f['path']}\n{f['content'][:2000]}"
        for f in files
        if f['content'] and not f['content'].startswith('(')
    )[:12000]

    analysis_prompt = (
        f"You are the Solution Architect studying an external codebase to clone and build on top of for project '{project_id}'.\n"
        f"Repo URL: {body.clone_url}\n\n"
        f"REPO STRUCTURE:\n{tree_summary}\n\n"
        f"KEY FILES:\n{key_contents}\n\n"
        f"Produce structured notes covering:\n"
        f"1. TECH STACK: languages, frameworks, libraries\n"
        f"2. ARCHITECTURE: patterns, folder structure, entry points\n"
        f"3. KEY COMPONENTS: main modules, their purposes\n"
        f"4. DATA MODEL: schemas, models, database\n"
        f"5. API SURFACE: endpoints, routes\n"
        f"6. BUILD & DEPLOY: scripts, configs, CI/CD\n"
        f"7. CONVENTIONS: naming, style, patterns to follow when extending\n"
        f"8. HOW TO EXTEND: what a developer needs to know to add features\n"
    )
    notes = ""
    try:
        result = llm_runtime.generate(team="solution_arch", requirement=analysis_prompt, prior_count=0, handoff_to="none")
        if result and result.content:
            notes = result.content
    except Exception:
        notes = f"Cloned repo analysis:\nFiles: {len(files)}\nStructure:\n{tree_summary[:3000]}"

    store = _get_firestore()
    # Use a structured prefix so downstream consumers can parse reliably
    repo_knowledge = f"{project_id}|cloned_repo|{body.clone_url}|{notes[:4000]}"
    for team in ALL_TEAMS:
        bank_id = f"team-{team}"
        try:
            store.retain(user.uid, project_id, bank_id, repo_knowledge)
        except Exception:
            pass
    file_index = f"{project_id}|cloned_repo_files|{body.clone_url}|" + ", ".join(f['path'] for f in files[:100])
    try:
        store.retain(user.uid, project_id, "team-solution_arch", file_index)
    except Exception:
        pass

    return {
        "status": "cloned",
        "clone_url": body.clone_url,
        "files_analyzed": len(files),
        "notes_length": len(notes),
        "notes_preview": notes[:500],
        "file_tree": [f["path"] for f in files[:60]],
    }



@app.get("/api/projects/{project_id}/memory-map/{bank_id}")
def get_memory_bank_detail(
    project_id: str,
    bank_id: str,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Return the actual items stored in a memory bank for display."""
    try:
        store = _get_firestore()
        items = store.recall(user.uid, project_id, bank_id, limit=50)
    except Exception:
        try:
            snapshot = memory.snapshot()
            items = snapshot.get(bank_id, [])
        except Exception:
            items = []
    # Parse items into structured entries
    entries = []
    for item in items:
        if not isinstance(item, str):
            continue
        # Items are stored as "project_id:summary:artifact_preview"
        parts = item.split(":", 2)
        pid = parts[0] if len(parts) > 0 else ""
        if pid != project_id:
            continue
        rest = parts[1] + (":" + parts[2] if len(parts) > 2 else "") if len(parts) > 1 else item
        # Categorize
        if rest.startswith("repo_knowledge:"):
            entries.append({"type": "knowledge", "content": rest[len("repo_knowledge:"):]})
        elif rest.startswith("repo_files:"):
            entries.append({"type": "file_index", "content": rest[len("repo_files:"):]})
        elif rest.startswith("user:"):
            entries.append({"type": "chat_user", "content": rest[len("user:"):]})
        elif rest.startswith("assistant:"):
            entries.append({"type": "chat_assistant", "content": rest[len("assistant:"):]})
        elif rest.startswith("decision:"):
            # decision:<type>:<title>
            dec_parts = rest[len("decision:"):].split(":", 1)
            entries.append({
                "type": "decision",
                "decision_type": dec_parts[0] if dec_parts else "",
                "content": dec_parts[1] if len(dec_parts) > 1 else rest,
            })
        else:
            entries.append({"type": "artifact", "content": rest})
    return {
        "project_id": project_id,
        "bank_id": bank_id,
        "total": len(entries),
        "items": entries,
    }


# ═══════════════════════════════════════════════════════════
#  SELF-HEAL  — error watchdog + auto-fix pipeline
# ═══════════════════════════════════════════════════════════

def _run_selfheal(heal_entry: dict, project_id: str, uid: str) -> None:
    """Run one full self-heal cycle: fix pipeline → sign-offs → optional merge."""
    try:
        analysis = heal_entry["analysis"]
        fix_req = RunRequest(
            project_id=project_id,
            requirement=f"[SELF-HEAL] {analysis['requirement']}",
        )
        fix_task_id = f"heal-{uuid.uuid4()}"
        heal_entry["fix_task_id"] = fix_task_id
        heal_entry["status"] = "fixing"

        fix_thread = threading.Thread(
            target=_run_full_pipeline_tracked,
            args=(fix_task_id, fix_req, uid),
            daemon=True,
        )
        fix_thread.start()
        fix_thread.join(timeout=360)  # wait up to 6 min

        fix_run = _task_store_load(fix_task_id) or {}
        fix_artifact = " ".join(
            act.get("artifact_preview", "") for act in fix_run.get("activities", [])
        )

        # Collect sign-offs
        heal_entry["status"] = "reviewing"
        agent = _get_self_heal_agent()
        signoffs = agent.get_agent_signoffs(
            fix_requirement=analysis["requirement"],
            fix_artifact=fix_artifact,
            teams=analysis.get("teams", ["backend_eng", "qa_eng"]),
        )
        heal_entry["signoffs"] = signoffs
        all_approved = all(s["approved"] for s in signoffs.values())

        # Auto-merge to dev if approved and git is configured
        merge_result = None
        if all_approved:
            try:
                git_cfg = _get_firestore().get_git_config(uid, project_id)
                if git_cfg and git_cfg.get("git_url"):
                    token = _get_firestore().get_git_token(uid) or ""
                    storage = fix_run.get("result", {}).get("storage", {})
                    fix_branch = storage.get("branch", "")
                    if fix_branch and token:
                        merge_result = _get_git().merge_branch(
                            git_url=git_cfg["git_url"],
                            git_token=token,
                            source_branch=fix_branch,
                            target_branch="dev",
                        )
            except Exception as merge_exc:
                merge_result = {"status": "failed", "error": str(merge_exc)}

        heal_entry["merge_result"] = merge_result
        heal_entry["status"] = "approved" if all_approved else "rejected"
        heal_entry["completed_at"] = datetime.now(UTC).isoformat()

        n_approved = sum(1 for s in signoffs.values() if s["approved"])
        n_total = len(signoffs)
        merged_ok = (merge_result or {}).get("status") in ("merged", "already_merged")
        if all_approved:
            heal_entry["notification"] = (
                f"✅ Self-heal complete: {analysis.get('root_cause','')[:80]} | "
                f"Signoffs: {n_approved}/{n_total} | "
                f"Merged to dev: {'yes' if merged_ok else 'no'}"
            )
        else:
            rejected = [t for t, s in signoffs.items() if not s["approved"]]
            heal_entry["notification"] = (
                f"⚠️ Self-heal rejected by: {', '.join(rejected)} | "
                f"Issue: {analysis.get('root_cause','')[:80]}"
            )
    except Exception as exc:
        log.warning("Self-heal cycle failed for %s: %s", project_id, exc)
        heal_entry["status"] = "failed"
        heal_entry["error"] = str(exc)
        heal_entry["completed_at"] = datetime.now(UTC).isoformat()
        heal_entry["notification"] = f"❌ Self-heal failed: {exc}"


def _watchdog_loop(
    watcher_key: str, project_id: str, uid: str, stop_event: threading.Event
) -> None:
    """Poll error buffer every 60 s; trigger self-heal when new errors appear."""
    log.info("Watchdog started: %s", watcher_key)
    while not stop_event.wait(60):
        try:
            with _error_buffer_lock:
                errors = list(_error_buffer[project_id])

            with _heal_history_lock:
                history = _heal_history[project_id]
                last_ts = history[-1]["started_at"] if history else "1970-01-01T00:00:00+00:00"

            new_errors = [e for e in errors if e["ts"] > last_ts]
            if not new_errors:
                continue

            log.info("Watchdog: %d new errors in %s — triggering self-heal",
                     len(new_errors), project_id)

            agent = _get_self_heal_agent()
            analysis = agent.analyze_issue(new_errors, project_id)
            if not analysis.get("requirement"):
                continue

            heal_entry = {
                "heal_id": str(uuid.uuid4())[:8],
                "project_id": project_id,
                "started_at": datetime.now(UTC).isoformat(),
                "status": "analyzing",
                "errors": new_errors[-5:],
                "analysis": analysis,
                "fix_task_id": None,
                "signoffs": {},
                "merge_result": None,
                "completed_at": None,
                "notification": "",
                "manual": False,
            }
            with _heal_history_lock:
                _heal_history[project_id].append(heal_entry)

            threading.Thread(
                target=_run_selfheal,
                args=(heal_entry, project_id, uid),
                daemon=True,
            ).start()

        except Exception as exc:
            log.warning("Watchdog error for %s: %s", project_id, exc)
    log.info("Watchdog stopped: %s", watcher_key)


@app.post("/api/projects/{project_id}/selfheal/start")
def start_selfheal_watcher(
    project_id: str,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Start the background error watchdog for this project."""
    watcher_key = f"{user.uid}:{project_id}"
    with _watchers_lock:
        if watcher_key in _watchers:
            return {"status": "already_running", "project_id": project_id}
        stop_event = threading.Event()
        _watchers[watcher_key] = stop_event
    threading.Thread(
        target=_watchdog_loop,
        args=(watcher_key, project_id, user.uid, stop_event),
        daemon=True,
    ).start()
    return {"status": "started", "project_id": project_id}


@app.post("/api/projects/{project_id}/selfheal/stop")
def stop_selfheal_watcher(
    project_id: str,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Stop the background error watchdog."""
    watcher_key = f"{user.uid}:{project_id}"
    with _watchers_lock:
        ev = _watchers.pop(watcher_key, None)
    if ev:
        ev.set()
        return {"status": "stopped", "project_id": project_id}
    return {"status": "not_running", "project_id": project_id}


@app.get("/api/projects/{project_id}/selfheal/status")
def selfheal_status(
    project_id: str,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Return watchdog state, recent errors, and heal history."""
    watcher_key = f"{user.uid}:{project_id}"
    with _watchers_lock:
        running = watcher_key in _watchers
    with _heal_history_lock:
        history = list(_heal_history[project_id])[-20:]
    with _error_buffer_lock:
        recent_errors = list(_error_buffer[project_id])[-10:]
    return {
        "running": running,
        "project_id": project_id,
        "history": history,
        "recent_errors": recent_errors,
        "notifications": [
            h["notification"] for h in history
            if h.get("notification") and h.get("status") in ("approved", "rejected", "failed")
        ][-5:],
    }


@app.post("/api/projects/{project_id}/selfheal/trigger")
def trigger_selfheal_manual(
    project_id: str,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Manually trigger one self-heal cycle on the current error buffer."""
    with _error_buffer_lock:
        errors = list(_error_buffer[project_id])
    if not errors:
        return {"status": "no_errors",
                "message": "Error buffer is empty — no issues to fix"}

    agent = _get_self_heal_agent()
    analysis = agent.analyze_issue(errors, project_id)
    if not analysis.get("requirement"):
        return {"status": "no_fix",
                "message": "Could not identify a specific fix for current errors"}

    heal_entry = {
        "heal_id": str(uuid.uuid4())[:8],
        "project_id": project_id,
        "started_at": datetime.now(UTC).isoformat(),
        "status": "analyzing",
        "errors": errors[-5:],
        "analysis": analysis,
        "fix_task_id": None,
        "signoffs": {},
        "merge_result": None,
        "completed_at": None,
        "notification": "",
        "manual": True,
    }
    with _heal_history_lock:
        _heal_history[project_id].append(heal_entry)

    threading.Thread(
        target=_run_selfheal,
        args=(heal_entry, project_id, user.uid),
        daemon=True,
    ).start()

    return {
        "status": "triggered",
        "heal_id": heal_entry["heal_id"],
        "project_id": project_id,
        "errors_analyzed": len(errors),
        "analysis": analysis,
    }


# ═══════════════════════════════════════════════════════════
#  A2A MESSAGE BUS — inspect inter-team messages
# ═══════════════════════════════════════════════════════════

@app.get("/api/a2a/messages")
def get_a2a_messages(
    team: str | None = None,
    limit: int = 50,
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Return recent A2A messages from the in-process bus (for observability)."""
    try:
        from factory.messaging.bus import get_bus
        bus = get_bus()
        messages = bus.message_log(team=team, limit=limit)
        stats = bus.team_stats()
        return {
            "messages": messages,
            "team_stats": stats,
            "filter_team": team,
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"A2A bus unavailable: {exc}")


@app.get("/api/a2a/teams/{team}/inbox")
def get_team_inbox(
    team: str,
    peek: bool = True,    # if True, don't consume messages
    user: AuthUser = Depends(get_current_user),
) -> dict:
    """Return queued messages for a team (peek mode by default)."""
    try:
        from factory.messaging.bus import get_bus
        bus = get_bus()
        if peek:
            msgs = [m.to_dict() for m in bus.peek(team)]
        else:
            msgs = [m.to_dict() for m in bus.receive_all(team)]
        return {
            "team": team,
            "mode": "peek" if peek else "drain",
            "count": len(msgs),
            "messages": msgs,
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"A2A bus unavailable: {exc}")
