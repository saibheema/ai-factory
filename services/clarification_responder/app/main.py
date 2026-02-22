import os
import threading

from fastapi import FastAPI

from factory.clarification.responder import ClarificationResponderWorker

app = FastAPI(title="AI Factory Clarification Responder", version="0.1.0")

worker: ClarificationResponderWorker | None = None
worker_thread: threading.Thread | None = None


def _teams() -> list[str]:
    value = os.getenv("RESPONDER_TEAMS", "biz_analysis,solution_arch,backend_eng,qa_eng,docs_team")
    return [x.strip() for x in value.split(",") if x.strip()]


@app.on_event("startup")
def startup() -> None:
    global worker, worker_thread
    worker = ClarificationResponderWorker(teams=_teams(), ttl_seconds=int(os.getenv("CLARIFICATION_TTL_SECONDS", "120")))
    worker_thread = threading.Thread(target=worker.run_forever, daemon=True)
    worker_thread.start()


@app.on_event("shutdown")
def shutdown() -> None:
    if worker:
        worker.stop()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "clarification_responder", "teams": _teams()}


@app.post("/run-once")
def run_once() -> dict:
    if not worker:
        return {"processed": 0, "status": "not-started"}
    return {"processed": worker.run_once(), "status": "ok"}
