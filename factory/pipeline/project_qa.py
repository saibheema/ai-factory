from dataclasses import dataclass
import re


@dataclass
class QAMatch:
    bank_id: str
    snippet: str
    score: float


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_]+", text.lower()))


def answer_project_question(project_id: str, question: str, memory_snapshot: dict[str, list[str]], top_k: int = 3) -> tuple[str, list[QAMatch]]:
    q = _tokens(question)
    matches: list[QAMatch] = []

    for bank_id, items in memory_snapshot.items():
        for item in items:
            if project_id not in item:
                continue
            item_tokens = _tokens(item)
            if not item_tokens:
                continue
            overlap = len(q & item_tokens)
            union = len(q | item_tokens) or 1
            score = overlap / union
            if score > 0:
                matches.append(QAMatch(bank_id=bank_id, snippet=item[:220], score=round(score, 4)))

    matches.sort(key=lambda m: m.score, reverse=True)
    top = matches[:top_k]

    if not top:
        return (
            "No strong memory match found for this project yet. Run the pipeline first or ask a more specific question.",
            [],
        )

    summary_bits = [f"{m.bank_id} (score={m.score})" for m in top]
    answer = "Most relevant project memory sources: " + ", ".join(summary_bits)
    return answer, top
