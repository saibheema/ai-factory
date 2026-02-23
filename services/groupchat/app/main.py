"""AI Factory Group Chat Service — v0.2.0

Runs a real multi-turn LLM discussion between nominated teams.
Each participant contributes in sequence; final consensus is produced
by the solution_arch team summarising the full discussion.
"""
import logging
import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

log = logging.getLogger(__name__)

# Ensure factory package is importable when running from service root
_factory_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _factory_root not in sys.path:
    sys.path.insert(0, _factory_root)

app = FastAPI(title="AI Factory Group Chat", version="0.2.0")

raw_allowed = os.getenv("ALLOWED_ORIGINS", "http://localhost:3001")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in raw_allowed.split(",") if x.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy-load LLM runtime to avoid import cost when ENABLE_LLM_RUNTIME=false
_runtime = None


def _get_runtime():
    global _runtime
    if _runtime is None:
        try:
            from factory.llm.runtime import TeamLLMRuntime
            _runtime = TeamLLMRuntime()
        except Exception as e:
            log.warning("Could not load TeamLLMRuntime: %s", e)
    return _runtime


# ── Models ────────────────────────────────────────────────────────────────────

class GroupPrompt(BaseModel):
    topic: str
    participants: list[str]


class DiscussRequest(BaseModel):
    topic: str
    participants: list[str]
    max_turns: int = 1          # how many rounds each participant speaks
    context: str = ""           # optional initial context


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    rt = _get_runtime()
    return {
        "status": "ok",
        "service": "groupchat",
        "version": "0.2.0",
        "llm_enabled": bool(rt and rt.enabled),
    }


@app.post("/session/plan")
def plan_session(req: GroupPrompt) -> dict:
    """Return a lightweight session plan (fast, no LLM call)."""
    return {
        "topic": req.topic,
        "participants": req.participants,
        "plan": [
            "align-on-goal",
            "split-by-team",
            "collect-findings",
            "synthesise-consensus",
            "define-action-items",
        ],
    }


@app.post("/session/discuss")
def discuss_session(req: DiscussRequest) -> dict:
    """Run a real multi-turn LLM discussion and return the transcript.

    Each participant produces a short message in the context of everything
    said before.  After all turns, the solution_arch team synthesises a
    consensus and extracts action items.
    """
    runtime = _get_runtime()
    discussion: list[dict] = []
    context_lines: list[str] = []

    if req.context:
        context_lines.append(f"Background:\n{req.context}")

    for _round in range(max(1, req.max_turns)):
        for participant in req.participants:
            prior = "\n".join(context_lines[-10:])  # last 10 lines of context
            prompt = (
                f"You are the {participant} team in a multi-team engineering discussion.\n\n"
                f"Topic: {req.topic}\n\n"
                f"{'Discussion so far:' + chr(10) + prior if prior else 'You are the first to speak.'}\n\n"
                f"Provide your team's key perspective, concerns, and recommendations "
                f"in 2-4 concise sentences. Be direct and technical."
            )

            message = f"[{participant}] No input available — LLM disabled."
            source = "fallback"

            if runtime and runtime.enabled:
                try:
                    result = runtime.generate(
                        team=participant,
                        requirement=prompt,
                        prior_count=0,
                        handoff_to="none",
                    )
                    if result and result.content:
                        message = result.content.strip()
                        source = result.source
                except Exception as exc:
                    log.warning("LLM call failed for %s: %s", participant, exc)

            discussion.append({
                "round": _round + 1,
                "team": participant,
                "message": message,
                "source": source,
            })
            context_lines.append(f"{participant}: {message[:300]}")

    # ── Synthesise consensus ──────────────────────────────────────────────
    full_transcript = "\n".join(
        f"{d['team']}: {d['message']}" for d in discussion
    )
    consensus = f"Teams reached consensus on: {req.topic}"
    action_items: list[str] = []

    if runtime and runtime.enabled:
        try:
            synth_prompt = (
                f"You are the solution architect summarising a team discussion.\n\n"
                f"Topic: {req.topic}\n\n"
                f"Discussion transcript:\n{full_transcript}\n\n"
                f"Respond in EXACTLY this format:\n"
                f"CONSENSUS: <one-sentence consensus statement>\n"
                f"ACTION_1: <first action item>\n"
                f"ACTION_2: <second action item>\n"
                f"ACTION_3: <third action item>\n"
            )
            synth = runtime.generate(
                team="solution_arch",
                requirement=synth_prompt,
                prior_count=0,
                handoff_to="none",
            )
            if synth and synth.content:
                for line in synth.content.splitlines():
                    if line.startswith("CONSENSUS:"):
                        consensus = line.split(":", 1)[1].strip()
                    elif line.startswith("ACTION_"):
                        item = line.split(":", 1)[1].strip()
                        if item:
                            action_items.append(item)
        except Exception as exc:
            log.warning("Consensus synthesis failed: %s", exc)

    if not action_items:
        action_items = [
            f"Implement the agreed solution for: {req.topic}",
            "Schedule a follow-up review in 48 hours",
            "Update project documentation with decisions made",
        ]

    return {
        "topic": req.topic,
        "participants": req.participants,
        "rounds": req.max_turns,
        "discussion": discussion,
        "consensus": consensus,
        "action_items": action_items,
    }

            "decide-next-actions",
        ],
    }
