from factory.clarification.responder import ClarificationResponderWorker


class FakeRedis:
    def __init__(self) -> None:
        self.replies: dict[str, str] = {}
        self._messages = [
            (
                "clarification.qa_eng",
                [("1-0", {"request_id": "req-1", "from_team": "backend_eng", "question": "Need AC"})],
            )
        ]

    def xread(self, streams, count, block):  # noqa: ANN001
        out = self._messages
        self._messages = []
        return out

    def setex(self, key: str, ttl: int, value: str) -> None:  # noqa: ARG002
        self.replies[key] = value


def test_responder_run_once_sets_reply() -> None:
    worker = ClarificationResponderWorker(teams=["qa_eng"], ttl_seconds=120)
    worker.redis = FakeRedis()  # type: ignore[assignment]

    processed = worker.run_once()

    assert processed == 1
    assert "clarification:reply:req-1" in worker.redis.replies
