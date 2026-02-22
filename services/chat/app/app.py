from fastapi import FastAPI

app = FastAPI(title="AI Factory Chat", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "chat", "phase": 1}
