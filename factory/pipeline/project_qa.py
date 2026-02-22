from dataclasses import dataclass
import os
import re

import httpx


@dataclass
class QAMatch:
    bank_id: str
    snippet: str
    score: float


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_]+", text.lower()))


def _call_llm(question: str, context: str) -> str:
    """Ask the LLM proxy to answer a question given memory context."""
    proxy_url = os.getenv("LITELLM_PROXY_URL", "http://litellm:4000")
    model = os.getenv("CHAT_MODEL", "factory/fast")
    prompt = (
        "You are a helpful AI assistant for a software project. "
        "Answer the user's question using ONLY the context below. "
        "If the context is insufficient, say so and offer general guidance.\n\n"
        f"=== Project Memory Context ===\n{context}\n\n"
        f"=== User Question ===\n{question}\n\n"
        "Answer concisely and helpfully:"
    )
    try:
        resp = httpx.post(
            f"{proxy_url}/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 600},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"(LLM unavailable: {e})"


def answer_project_question(
    project_id: str,
    question: str,
    memory_snapshot: dict[str, list[str]],
    top_k: int = 5,
) -> tuple[str, list[QAMatch]]:
    q = _tokens(question)
    matches: list[QAMatch] = []

    for bank_id, items in memory_snapshot.items():
        for item in items:
            item_tokens = _tokens(item)
            if not item_tokens:
                continue
            overlap = len(q & item_tokens)
            union = len(q | item_tokens) or 1
            score = overlap / union
            if score > 0:
                matches.append(QAMatch(bank_id=bank_id, snippet=item[:300], score=round(score, 4)))

    matches.sort(key=lambda m: m.score, reverse=True)
    top = matches[:top_k]

    if not top:
        # Still try LLM with no context — it can answer general questions
        answer = _call_llm(question, "No project memory available yet. Pipeline has not been run for this project.")
        return answer, []

    # Build context from top matches — prefer items that look like real artifacts
    context_parts = []
    for m in top:
        label = m.bank_id.replace("_", " ").replace("-", " ")
        context_parts.append(f"[{label}]\n{m.snippet}")
    context = "\n\n".join(context_parts)

    answer = _call_llm(question, context)
    return answer, top
