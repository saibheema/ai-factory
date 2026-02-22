import logging
import os
from datetime import UTC, datetime
from typing import Any


class LangfuseTracer:
    """Best-effort tracer wrapper. No-op when SDK/config is unavailable."""

    def __init__(self) -> None:
        self.enabled = os.getenv("LANGFUSE_ENABLED", "false").lower() == "true"
        self._logger = logging.getLogger("ai_factory.langfuse")
        self._client = None
        if not self.enabled:
            return
        try:
            from langfuse import Langfuse  # type: ignore

            self._client = Langfuse(
                public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
                secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
                host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            )
        except Exception as exc:  # pragma: no cover
            self._logger.warning("Langfuse disabled; SDK unavailable: %s", exc)
            self._client = None

    def event(self, name: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        timestamp = datetime.now(UTC).isoformat()
        data = {"timestamp": timestamp, **payload}

        if self._client is None:
            self._logger.info("langfuse_event name=%s payload=%s", name, data)
            return

        try:
            self._client.create_event(name=name, metadata=data)
            self._client.flush()
        except Exception as exc:  # pragma: no cover
            self._logger.warning("Langfuse event failed: %s", exc)
