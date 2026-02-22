from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import redis


@dataclass
class ClarificationRequest:
    id: str
    from_team: str
    to_team: str
    question: str
    expires_at: datetime


class ClarificationBroker:
    def __init__(self, ttl_seconds: int = 120) -> None:
        self.ttl_seconds = ttl_seconds
        self._requests: dict[str, ClarificationRequest] = {}
        self._responses: dict[str, str] = {}
        self._redis = self._build_redis_client()

    def _build_redis_client(self) -> redis.Redis | None:
        try:
            host = os.getenv("REDIS_HOST", "redis")
            port = int(os.getenv("REDIS_PORT", "6379"))
            password = os.getenv("REDIS_PASSWORD") or None
            client = redis.Redis(host=host, port=port, password=password, decode_responses=True)
            client.ping()
            return client
        except Exception:
            return None

    def request(self, from_team: str, to_team: str, question: str) -> ClarificationRequest:
        req = ClarificationRequest(
            id=str(uuid4()),
            from_team=from_team,
            to_team=to_team,
            question=question,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.ttl_seconds),
        )
        self._requests[req.id] = req
        if self._redis is not None:
            self._redis.xadd(
                f"clarification.{to_team}",
                {
                    "request_id": req.id,
                    "from_team": from_team,
                    "to_team": to_team,
                    "question": question,
                    "expires_at": req.expires_at.isoformat(),
                },
            )
        return req

    def respond(self, request_id: str, answer: str) -> None:
        self._responses[request_id] = answer
        if self._redis is not None:
            self._redis.setex(f"clarification:reply:{request_id}", self.ttl_seconds, answer)

    def get_response(self, request_id: str) -> str | None:
        req = self._requests.get(request_id)
        if not req:
            return None
        if datetime.now(UTC) > req.expires_at:
            return "TIMEOUT"

        if self._redis is not None:
            value = self._redis.get(f"clarification:reply:{request_id}")
            if value:
                return value

        return self._responses.get(request_id)
