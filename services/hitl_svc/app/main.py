"""HITL (Human-in-the-Loop) Service — v0.1.0

Escalation bridge between AI agents and human operators.

Flow
----
1. An agent / orchestrator calls ``POST /hitl/requests`` when it needs
   a human decision (e.g. an ambiguous requirement, budget approval, legal review).
2. The UI polls ``GET /hitl/pending`` and renders the question.
3. A human operator submits a decision via ``POST /hitl/requests/{id}/respond``.
4. The orchestrator polls ``GET /hitl/requests/{id}`` until status == "resolved",
   then continues the pipeline with the human decision.
"""
import logging
import os
import uuid
from datetime import UTC, datetime
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

app = FastAPI(title="AI Factory HITL Service", version="0.1.0")

raw_allowed = os.getenv("ALLOWED_ORIGINS", "http://localhost:3001")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in raw_allowed.split(",") if x.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory store (persisted to Firestore if available) ────────────────────
_requests: dict[str, dict] = {}
_lock = Lock()

_URGENCY_LEVELS = {"low", "normal", "high", "critical"}

# ── Models ────────────────────────────────────────────────────────────────────


class HITLSubmitRequest(BaseModel):
    project_id: str = Field(min_length=1)
    task_id: str | None = None
    team: str = Field(min_length=2)
    question: str = Field(min_length=5)
    context: str = ""
    urgency: str = "normal"
    options: list[str] = Field(default_factory=list)   # optional choice list for the UI


class HITLRespondRequest(BaseModel):
    decision: str = Field(min_length=1)
    comment: str = ""


# ── Helper ────────────────────────────────────────────────────────────────────


def _try_firestore_save(entry: dict) -> None:
    """Best-effort Firestore persistence — never blocks the response."""
    try:
        from factory.persistence.firestore_store import FirestoreStore
        fs = FirestoreStore()
        fs._db().collection("hitl_requests").document(entry["id"]).set(entry)
    except Exception as exc:
        log.debug("Firestore HITL save skipped: %s", exc)


def _try_firestore_update(request_id: str, patch: dict) -> None:
    try:
        from factory.persistence.firestore_store import FirestoreStore
        fs = FirestoreStore()
        fs._db().collection("hitl_requests").document(request_id).update(patch)
    except Exception as exc:
        log.debug("Firestore HITL update skipped: %s", exc)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict:
    with _lock:
        pending = sum(1 for r in _requests.values() if r["status"] == "pending")
        total = len(_requests)
    return {
        "status": "ok",
        "service": "hitl",
        "version": "0.1.0",
        "pending_requests": pending,
        "total_requests": total,
    }


@app.post("/hitl/requests", status_code=201)
def submit_request(req: HITLSubmitRequest) -> dict:
    """Agent submits a new escalation request requiring human input."""
    urgency = req.urgency if req.urgency in _URGENCY_LEVELS else "normal"
    rid = str(uuid.uuid4())
    entry = {
        "id": rid,
        "project_id": req.project_id,
        "task_id": req.task_id,
        "team": req.team,
        "question": req.question,
        "context": req.context[:2000],    # cap to avoid huge payloads
        "urgency": urgency,
        "options": req.options,
        "status": "pending",
        "created_at": datetime.now(UTC).isoformat(),
        "resolved_at": None,
        "decision": None,
        "comment": "",
    }
    with _lock:
        _requests[rid] = entry
    _try_firestore_save(entry)
    log.info(
        "HITL request %s submitted: project=%s team=%s urgency=%s",
        rid, req.project_id, req.team, urgency,
    )
    return {"id": rid, "status": "pending", "created_at": entry["created_at"]}


@app.get("/hitl/pending")
def list_pending(project_id: str | None = None) -> dict:
    """UI polls this endpoint to show pending escalation requests."""
    with _lock:
        all_pending = [
            v for v in _requests.values() if v["status"] == "pending"
        ]
    if project_id:
        all_pending = [r for r in all_pending if r["project_id"] == project_id]
    all_pending.sort(
        key=lambda r: (
            {"critical": 0, "high": 1, "normal": 2, "low": 3}.get(r["urgency"], 2),
            r["created_at"],
        )
    )
    return {"count": len(all_pending), "requests": all_pending}


@app.get("/hitl/requests/{request_id}")
def get_request(request_id: str) -> dict:
    """Orchestrator polls this to check if a pending request has been resolved."""
    with _lock:
        req = _requests.get(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="HITL request not found")
    return req


@app.post("/hitl/requests/{request_id}/respond")
def respond_to_request(request_id: str, resp: HITLRespondRequest) -> dict:
    """Human operator submits their decision via the UI."""
    with _lock:
        req = _requests.get(request_id)
        if req is None:
            raise HTTPException(status_code=404, detail="HITL request not found")
        if req["status"] != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"Request already in state '{req['status']}' — cannot respond again",
            )
        resolved_at = datetime.now(UTC).isoformat()
        req["status"] = "resolved"
        req["decision"] = resp.decision
        req["comment"] = resp.comment
        req["resolved_at"] = resolved_at

    patch = {
        "status": "resolved",
        "decision": resp.decision,
        "comment": resp.comment,
        "resolved_at": resolved_at,
    }
    _try_firestore_update(request_id, patch)
    log.info(
        "HITL request %s resolved: decision=%s", request_id, resp.decision[:80]
    )
    return {
        "id": request_id,
        "status": "resolved",
        "decision": resp.decision,
        "resolved_at": resolved_at,
    }


@app.delete("/hitl/requests/{request_id}")
def delete_request(request_id: str) -> dict:
    """Remove a resolved or stale request from the store."""
    with _lock:
        req = _requests.pop(request_id, None)
    if req is None:
        raise HTTPException(status_code=404, detail="HITL request not found")
    return {"id": request_id, "status": "deleted"}


@app.get("/hitl/all")
def list_all(project_id: str | None = None) -> dict:
    """Admin view — all requests regardless of status."""
    with _lock:
        all_reqs = list(_requests.values())
    if project_id:
        all_reqs = [r for r in all_reqs if r["project_id"] == project_id]
    all_reqs.sort(key=lambda r: r["created_at"])
    return {
        "count": len(all_reqs),
        "pending": sum(1 for r in all_reqs if r["status"] == "pending"),
        "resolved": sum(1 for r in all_reqs if r["status"] == "resolved"),
        "requests": all_reqs,
    }
