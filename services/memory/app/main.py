from collections import defaultdict
import logging
import os

from fastapi import FastAPI
from pydantic import BaseModel

log = logging.getLogger(__name__)

try:
    import psycopg
except Exception:  # pragma: no cover
    psycopg = None

# ── Optional: sentence-transformers for semantic embeddings ──────────────────
try:
    from sentence_transformers import SentenceTransformer as _ST  # type: ignore
    _embed_model = _ST("all-MiniLM-L6-v2")  # 384-dim, ~90 MB
    _EMBED_DIM = 384
    log.info("sentence-transformers loaded — semantic search enabled")
except Exception:
    _embed_model = None
    _EMBED_DIM = 0

app = FastAPI(title="AI Factory Memory Service", version="0.2.0")

banks: dict[str, list[str]] = defaultdict(list)

# Track whether pgvector extension is available
_pgvector_enabled = False


def _db_params() -> dict[str, str | int] | None:
    host = os.getenv("DB_HOST")
    name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    port = os.getenv("DB_PORT", "5432")

    if not host or not name or not user or not password:
        return None
    if psycopg is None:
        return None
    return {
        "host": host,
        "port": int(port),
        "dbname": name,
        "user": user,
        "password": password,
    }


def _init_db() -> None:
    global _pgvector_enabled
    params = _db_params()
    if not params:
        return
    try:
        with psycopg.connect(**params) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memory_items (
                        id BIGSERIAL PRIMARY KEY,
                        bank_id TEXT NOT NULL,
                        item TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memory_bank_created "
                    "ON memory_items(bank_id, created_at)"
                )
                # Try to enable pgvector extension and add embedding column
                try:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                    if _EMBED_DIM > 0:
                        cur.execute(
                            f"ALTER TABLE memory_items "
                            f"ADD COLUMN IF NOT EXISTS embedding vector({_EMBED_DIM})"
                        )
                        cur.execute(
                            "CREATE INDEX IF NOT EXISTS idx_memory_embedding "
                            "ON memory_items USING ivfflat (embedding vector_cosine_ops) "
                            "WITH (lists = 20)"
                        )
                    _pgvector_enabled = True
                    log.info("pgvector extension enabled")
                except Exception as _ve:
                    log.info("pgvector not available, using text search: %s", _ve)
                    _pgvector_enabled = False
            conn.commit()
    except Exception:
        # Keep service available and fall back to in-memory mode.
        return


def _retain_db(bank_id: str, item: str) -> bool:
    params = _db_params()
    if not params:
        return False
    try:
        embedding: list[float] | None = None
        if _pgvector_enabled and _embed_model is not None and _EMBED_DIM > 0:
            try:
                embedding = _embed_model.encode(item).tolist()
            except Exception:
                embedding = None

        with psycopg.connect(**params) as conn:
            with conn.cursor() as cur:
                if embedding is not None:
                    cur.execute(
                        "INSERT INTO memory_items(bank_id, item, embedding) "
                        "VALUES (%s, %s, %s::vector)",
                        (bank_id, item, str(embedding)),
                    )
                else:
                    cur.execute(
                        "INSERT INTO memory_items(bank_id, item) VALUES (%s, %s)",
                        (bank_id, item),
                    )
            conn.commit()
        return True
    except Exception:
        return False


def _recall_db(bank_id: str, limit: int) -> list[str] | None:
    params = _db_params()
    if not params:
        return None
    try:
        with psycopg.connect(**params) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT item
                    FROM memory_items
                    WHERE bank_id = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s
                    """,
                    (bank_id, limit),
                )
                rows = cur.fetchall()
        return [row[0] for row in reversed(rows)]
    except Exception:
        return None


def _snapshot_db() -> dict[str, list[str]] | None:
    params = _db_params()
    if not params:
        return None
    try:
        grouped: dict[str, list[str]] = defaultdict(list)
        with psycopg.connect(**params) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT bank_id, item
                    FROM memory_items
                    ORDER BY created_at ASC, id ASC
                    """
                )
                for bank_id, item in cur.fetchall():
                    grouped[bank_id].append(item)
        return dict(grouped)
    except Exception:
        return None


def _search_vector_db(bank_id: str, embedding: list[float], limit: int) -> list[str] | None:
    """Cosine similarity search using pgvector <=> operator."""
    params = _db_params()
    if not params or not _pgvector_enabled:
        return None
    try:
        with psycopg.connect(**params) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT item
                    FROM memory_items
                    WHERE bank_id = %s AND embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (bank_id, str(embedding), limit),
                )
                rows = cur.fetchall()
        return [row[0] for row in rows]
    except Exception:
        return None


def _search_text_db(bank_id: str, query: str, limit: int) -> list[str] | None:
    """PostgreSQL full-text search fallback (ILIKE)."""
    params = _db_params()
    if not params:
        return None
    try:
        with psycopg.connect(**params) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT item
                    FROM memory_items
                    WHERE bank_id = %s AND item ILIKE %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (bank_id, f"%{query}%", limit),
                )
                rows = cur.fetchall()
        return [row[0] for row in rows]
    except Exception:
        return None


def _count_bank_db(bank_id: str) -> int | None:
    """Return the total number of items in a bank."""
    params = _db_params()
    if not params:
        return None
    try:
        with psycopg.connect(**params) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM memory_items WHERE bank_id = %s",
                    (bank_id,),
                )
                row = cur.fetchone()
        return row[0] if row else 0
    except Exception:
        return None


def _compress_db(bank_id: str, keep_last: int = 10) -> int:
    """Delete old items keeping only the most recent `keep_last`."""
    params = _db_params()
    if not params:
        return 0
    try:
        with psycopg.connect(**params) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM memory_items
                    WHERE bank_id = %s
                      AND id NOT IN (
                        SELECT id FROM memory_items
                        WHERE bank_id = %s
                        ORDER BY created_at DESC, id DESC
                        LIMIT %s
                      )
                    """,
                    (bank_id, bank_id, keep_last),
                )
                deleted = cur.rowcount
            conn.commit()
        return deleted
    except Exception:
        return 0


class RetainRequest(BaseModel):
    item: str


@app.on_event("startup")
def startup() -> None:
    _init_db()


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "memory",
        "version": "0.2.0",
        "pgvector": _pgvector_enabled,
        "semantic_search": _embed_model is not None,
    }


@app.get("/banks/{bank_id}/recall")
def recall(bank_id: str, limit: int = 5) -> dict:
    db_items = _recall_db(bank_id, limit)
    if db_items is not None:
        return {"bank_id": bank_id, "items": db_items, "store": "postgres"}
    return {"bank_id": bank_id, "items": banks[bank_id][-limit:], "store": "memory"}


@app.post("/banks/{bank_id}/retain")
def retain(bank_id: str, req: RetainRequest) -> dict:
    if _retain_db(bank_id, req.item):
        return {"bank_id": bank_id, "status": "stored", "store": "postgres"}
    banks[bank_id].append(req.item)
    return {"bank_id": bank_id, "size": len(banks[bank_id]), "store": "memory"}


@app.get("/banks/snapshot")
def snapshot() -> dict:
    db_snapshot = _snapshot_db()
    if db_snapshot is not None:
        return {"banks": db_snapshot, "store": "postgres"}
    return {"banks": dict(banks), "store": "memory"}


@app.get("/banks/{bank_id}/search")
def semantic_search(bank_id: str, q: str, limit: int = 5) -> dict:
    """Semantic similarity search over a memory bank.

    Uses pgvector cosine similarity if available, falls back to
    PostgreSQL ILIKE text search, then in-memory substring match.
    """
    if not q.strip():
        return {"bank_id": bank_id, "query": q, "results": [], "method": "empty"}

    # ── Vector search ──────────────────────────────────────────────────────
    if _pgvector_enabled and _embed_model is not None:
        try:
            embedding = _embed_model.encode(q).tolist()
            results = _search_vector_db(bank_id, embedding, limit)
            if results is not None:
                return {
                    "bank_id": bank_id,
                    "query": q,
                    "results": results,
                    "method": "pgvector-cosine",
                }
        except Exception:
            pass

    # ── PostgreSQL ILIKE text search ──────────────────────────────────────
    results = _search_text_db(bank_id, q, limit)
    if results is not None:
        return {
            "bank_id": bank_id,
            "query": q,
            "results": results,
            "method": "postgres-ilike",
        }

    # ── In-memory substring match ─────────────────────────────────────────
    q_lower = q.lower()
    matched = [item for item in banks[bank_id] if q_lower in item.lower()]
    return {
        "bank_id": bank_id,
        "query": q,
        "results": matched[-limit:],
        "method": "memory-substring",
    }


@app.post("/banks/{bank_id}/compress")
def compress_bank(bank_id: str, keep_last: int = 15) -> dict:
    """Compress a memory bank by removing old items, keeping the most recent ones.

    Returns a summary of the compression operation.
    """
    # Check current size
    db_count = _count_bank_db(bank_id)
    if db_count is not None:
        if db_count <= keep_last:
            return {
                "bank_id": bank_id,
                "store": "postgres",
                "action": "skipped",
                "reason": f"bank has {db_count} items ≤ keep_last={keep_last}",
                "items_before": db_count,
                "items_removed": 0,
                "items_after": db_count,
            }
        deleted = _compress_db(bank_id, keep_last)
        return {
            "bank_id": bank_id,
            "store": "postgres",
            "action": "compressed",
            "items_before": db_count,
            "items_removed": deleted,
            "items_after": db_count - deleted,
        }

    # In-memory fallback
    current = banks[bank_id]
    if len(current) <= keep_last:
        return {
            "bank_id": bank_id,
            "store": "memory",
            "action": "skipped",
            "items_before": len(current),
            "items_removed": 0,
            "items_after": len(current),
        }
    removed = len(current) - keep_last
    banks[bank_id] = current[-keep_last:]
    return {
        "bank_id": bank_id,
        "store": "memory",
        "action": "compressed",
        "items_before": len(current),
        "items_removed": removed,
        "items_after": keep_last,
    }


@app.get("/banks/{bank_id}/stats")
def bank_stats(bank_id: str) -> dict:
    """Return size and metadata for a memory bank."""
    db_count = _count_bank_db(bank_id)
    if db_count is not None:
        return {
            "bank_id": bank_id,
            "count": db_count,
            "store": "postgres",
            "pgvector_enabled": _pgvector_enabled,
        }
    return {
        "bank_id": bank_id,
        "count": len(banks[bank_id]),
        "store": "memory",
        "pgvector_enabled": False,
    }
