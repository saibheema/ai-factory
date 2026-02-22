from collections import defaultdict
import os

from fastapi import FastAPI
from pydantic import BaseModel

try:
    import psycopg
except Exception:  # pragma: no cover
    psycopg = None

app = FastAPI(title="AI Factory Memory Service", version="0.1.0")

banks: dict[str, list[str]] = defaultdict(list)


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
                cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_bank_created ON memory_items(bank_id, created_at)")
            conn.commit()
    except Exception:
        # Keep service available and fall back to in-memory mode.
        return


def _retain_db(bank_id: str, item: str) -> bool:
    params = _db_params()
    if not params:
        return False
    try:
        with psycopg.connect(**params) as conn:
            with conn.cursor() as cur:
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


class RetainRequest(BaseModel):
    item: str


@app.on_event("startup")
def startup() -> None:
    _init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "memory", "phase": 1}


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
