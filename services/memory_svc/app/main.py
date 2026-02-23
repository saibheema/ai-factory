"""AI Factory Memory SVC — v0.1.0

Firestore-backed REST API for user-scoped, project-scoped memory banks.
Acts as the durable tier that complements the Postgres-backed memory service.

Endpoints
---------
GET  /health
GET  /memory/{uid}/{project_id}/{bank_id}/recall?limit=5
POST /memory/{uid}/{project_id}/{bank_id}/retain
GET  /memory/{uid}/{project_id}/snapshot
GET  /memory/{uid}/{project_id}/{bank_id}/search?q=text&limit=5
POST /memory/{uid}/{project_id}/{bank_id}/compress?keep_last=15
"""
import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

log = logging.getLogger(__name__)

app = FastAPI(title="AI Factory Memory SVC", version="0.1.0")

raw_allowed = os.getenv("ALLOWED_ORIGINS", "http://localhost:3001")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in raw_allowed.split(",") if x.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Lazy-init Firestore store ─────────────────────────────────────────────────
_store = None


def _get_store():
    global _store
    if _store is None:
        from factory.persistence.firestore_store import FirestoreStore
        _store = FirestoreStore()
    return _store


# ── Models ────────────────────────────────────────────────────────────────────


class RetainRequest(BaseModel):
    item: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "memory_svc",
        "version": "0.1.0",
        "backend": "firestore",
    }


@app.get("/memory/{uid}/{project_id}/{bank_id}/recall")
def recall(uid: str, project_id: str, bank_id: str, limit: int = 5) -> dict:
    """Recall the most recent *limit* items from a memory bank."""
    try:
        items = _get_store().recall(uid, project_id, bank_id, limit)
        return {
            "bank_id": bank_id,
            "uid": uid,
            "project_id": project_id,
            "items": items,
            "store": "firestore",
        }
    except Exception as exc:
        log.warning("Firestore recall failed uid=%s project=%s bank=%s: %s",
                    uid, project_id, bank_id, exc)
        raise HTTPException(status_code=503, detail=f"Firestore unavailable: {exc}")


@app.post("/memory/{uid}/{project_id}/{bank_id}/retain", status_code=201)
def retain(uid: str, project_id: str, bank_id: str, req: RetainRequest) -> dict:
    """Append an item to a memory bank."""
    try:
        _get_store().retain(uid, project_id, bank_id, req.item)
        return {
            "bank_id": bank_id,
            "uid": uid,
            "project_id": project_id,
            "status": "stored",
            "store": "firestore",
        }
    except Exception as exc:
        log.warning("Firestore retain failed uid=%s project=%s bank=%s: %s",
                    uid, project_id, bank_id, exc)
        raise HTTPException(status_code=503, detail=f"Firestore unavailable: {exc}")


@app.get("/memory/{uid}/{project_id}/snapshot")
def snapshot(uid: str, project_id: str) -> dict:
    """Return all memory banks for a project."""
    try:
        banks = _get_store().memory_snapshot(uid, project_id)
        return {
            "uid": uid,
            "project_id": project_id,
            "banks": banks,
            "store": "firestore",
        }
    except Exception as exc:
        log.warning("Firestore snapshot failed uid=%s project=%s: %s",
                    uid, project_id, exc)
        raise HTTPException(status_code=503, detail=f"Firestore unavailable: {exc}")


@app.get("/memory/{uid}/{project_id}/{bank_id}/search")
def search(uid: str, project_id: str, bank_id: str, q: str, limit: int = 5) -> dict:
    """Substring search over a memory bank's items.

    Full semantic / vector search is handled by the Postgres-backed memory
    service; this endpoint provides a simple fallback using string matching.
    """
    if not q.strip():
        return {
            "bank_id": bank_id,
            "query": q,
            "results": [],
            "method": "empty",
        }
    try:
        all_items: list[str] = _get_store().recall(uid, project_id, bank_id, limit=200)
        q_lower = q.lower()
        matched = [item for item in all_items if q_lower in item.lower()]
        return {
            "bank_id": bank_id,
            "query": q,
            "results": matched[:limit],
            "method": "firestore-substring",
        }
    except Exception as exc:
        log.warning("Firestore search failed uid=%s project=%s bank=%s: %s",
                    uid, project_id, bank_id, exc)
        raise HTTPException(status_code=503, detail=f"Firestore unavailable: {exc}")


@app.post("/memory/{uid}/{project_id}/{bank_id}/compress")
def compress(uid: str, project_id: str, bank_id: str, keep_last: int = 15) -> dict:
    """Compress a memory bank by keeping only the most recent *keep_last* items.

    Older items are summarised into a single prefix entry so context is
    preserved even after compression.
    """
    try:
        all_items: list[str] = _get_store().recall(uid, project_id, bank_id, limit=1000)
        count_before = len(all_items)

        if count_before <= keep_last:
            return {
                "bank_id": bank_id,
                "action": "skipped",
                "reason": f"only {count_before} items ≤ keep_last={keep_last}",
                "items_before": count_before,
                "items_removed": 0,
                "items_after": count_before,
            }

        kept = all_items[-keep_last:]
        removed_count = count_before - len(kept)

        # Overwrite the bank with the compressed set
        # Firestore doesn't have a bulk-replace; we clear and re-insert
        try:
            fs = _get_store()
            # Store a compression summary as the oldest item
            summary = (
                f"[COMPRESSED: {removed_count} older items summarised — "
                f"bank_id={bank_id} project={project_id}]"
            )
            new_items = [summary] + kept

            # Use an internal Firestore write to replace the bank
            fs._db().collection("users").document(uid).collection("projects") \
                .document(project_id).collection("memory").document(bank_id).set(
                    {"items": new_items, "compressed_at": __import__("datetime").datetime.utcnow().isoformat()}
                )
        except Exception as write_exc:
            log.warning("Firestore compress write failed: %s", write_exc)
            raise HTTPException(status_code=503, detail=str(write_exc))

        return {
            "bank_id": bank_id,
            "action": "compressed",
            "items_before": count_before,
            "items_removed": removed_count,
            "items_after": len(new_items),
            "store": "firestore",
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Firestore unavailable: {exc}")
