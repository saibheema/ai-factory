import os
import time
from typing import Iterable

import redis


class ClarificationResponderWorker:
    def __init__(self, teams: Iterable[str], ttl_seconds: int = 120) -> None:
        self.teams = [t.strip() for t in teams if t.strip()]
        self.ttl_seconds = ttl_seconds
        self._running = False
        self._last_ids: dict[str, str] = {team: "$" for team in self.teams}

        host = os.getenv("REDIS_HOST", "redis")
        port = int(os.getenv("REDIS_PORT", "6379"))
        password = os.getenv("REDIS_PASSWORD") or None
        self.redis = redis.Redis(host=host, port=port, password=password, decode_responses=True)

    def _response_text(self, target_team: str, from_team: str, question: str) -> str:
        return (
            f"[{target_team}] clarification response for {from_team}: "
            f"received '{question}'. Proceed with documented acceptance criteria and phase-1 defaults."
        )

    def run_once(self) -> int:
        if not self.teams:
            return 0

        streams = {f"clarification.{team}": self._last_ids[team] for team in self.teams}
        messages = self.redis.xread(streams=streams, count=10, block=1000)

        processed = 0
        for stream_name, entries in messages:
            team = stream_name.split("clarification.")[-1]
            for message_id, fields in entries:
                request_id = fields.get("request_id")
                from_team = fields.get("from_team", "unknown")
                question = fields.get("question", "")
                if request_id:
                    answer = self._response_text(team, from_team, question)
                    self.redis.setex(f"clarification:reply:{request_id}", self.ttl_seconds, answer)
                    processed += 1
                self._last_ids[team] = message_id

        return processed

    def run_forever(self, sleep_seconds: float = 0.2) -> None:
        self._running = True
        while self._running:
            try:
                self.run_once()
            except Exception:
                time.sleep(max(sleep_seconds, 0.5))
            else:
                time.sleep(sleep_seconds)

    def stop(self) -> None:
        self._running = False
