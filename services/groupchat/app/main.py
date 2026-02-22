from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="AI Factory Group Chat", version="0.1.0")


class GroupPrompt(BaseModel):
    topic: str
    participants: list[str]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "groupchat", "phase": 2}


@app.post("/session/plan")
def plan_session(req: GroupPrompt) -> dict:
    return {
        "topic": req.topic,
        "participants": req.participants,
        "plan": [
            "align-on-goal",
            "split-by-team",
            "collect-findings",
            "decide-next-actions",
        ],
    }
