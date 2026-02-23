"""In-process A2A message bus — thread-safe queue-per-team.

Design
------
* One ``queue.Queue`` per team, lazily created on first use.
* ``send()`` is non-blocking; if a queue is full the oldest message is
  silently dropped to make room (avoids back-pressure stalling agents).
* ``receive()`` is non-blocking by default (timeout=0); pass timeout > 0
  for a blocking receive with deadline.
* A bounded in-memory audit log is kept for observability.

The singleton ``_bus`` is module-level so all imports share the same
queues within a single process.  For multi-process deployments replace
the backend with Redis Streams (swap out ``queue.Queue``).
"""
from __future__ import annotations

import logging
import queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

log = logging.getLogger(__name__)

_MAX_QUEUE_SIZE = 500        # per-team queue capacity
_LOG_CAPACITY = 2000         # global audit log size


@dataclass
class Message:
    id: str
    from_team: str
    to_team: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from": self.from_team,
            "to": self.to_team,
            "content": self.content[:500],
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class MessageBus:
    """Thread-safe, in-process A2A message bus."""

    def __init__(self) -> None:
        self._queues: dict[str, queue.Queue] = {}
        self._lock = threading.Lock()
        # Circular audit log — most-recent entries only
        self._log: list[Message] = []
        self._log_lock = threading.Lock()

    # ── Internal ──────────────────────────────────────────────────────────

    def _get_queue(self, team: str) -> queue.Queue:
        with self._lock:
            if team not in self._queues:
                self._queues[team] = queue.Queue(maxsize=_MAX_QUEUE_SIZE)
            return self._queues[team]

    def _append_log(self, msg: Message) -> None:
        with self._log_lock:
            self._log.append(msg)
            if len(self._log) > _LOG_CAPACITY:
                self._log = self._log[-_LOG_CAPACITY:]

    # ── Public API ────────────────────────────────────────────────────────

    def send(
        self,
        to_team: str,
        from_team: str,
        content: str,
        metadata: dict | None = None,
    ) -> str:
        """Enqueue a message for ``to_team``.  Returns the message ID.

        If the queue is full the oldest message is evicted to make room
        so that senders are never blocked.
        """
        msg = Message(
            id=str(uuid.uuid4())[:8],
            from_team=from_team,
            to_team=to_team,
            content=content,
            metadata=metadata or {},
        )
        q = self._get_queue(to_team)
        try:
            q.put_nowait(msg)
        except queue.Full:
            try:
                q.get_nowait()          # drop oldest
                q.put_nowait(msg)
            except Exception:
                pass
        self._append_log(msg)
        log.debug("A2A: %s → %s  [%s]", from_team, to_team, msg.id)
        return msg.id

    def receive(self, team: str, timeout: float = 0.0) -> Message | None:
        """Dequeue the next message for ``team``.

        Parameters
        ----------
        timeout:
            Seconds to wait for a message.  0 = non-blocking (default).
            Positive float = block up to that many seconds.
        """
        q = self._get_queue(team)
        try:
            if timeout > 0:
                return q.get(block=True, timeout=timeout)
            return q.get_nowait()
        except (queue.Empty, Exception):
            return None

    def receive_all(self, team: str) -> list[Message]:
        """Drain all currently queued messages for ``team`` (non-blocking)."""
        q = self._get_queue(team)
        messages: list[Message] = []
        while True:
            try:
                messages.append(q.get_nowait())
            except queue.Empty:
                break
        return messages

    def peek(self, team: str) -> list[Message]:
        """Return a snapshot of the queue without consuming messages."""
        q = self._get_queue(team)
        with q.mutex:
            return list(q.queue)

    def queue_size(self, team: str) -> int:
        return self._get_queue(team).qsize()

    def message_log(
        self,
        team: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Return recent messages from the audit log."""
        with self._log_lock:
            msgs = self._log[-limit:]
        if team:
            msgs = [m for m in msgs if m.to_team == team or m.from_team == team]
        return [m.to_dict() for m in msgs]

    def team_stats(self) -> dict[str, dict]:
        """Return queue depths for all known teams."""
        with self._lock:
            teams = list(self._queues.keys())
        return {t: {"queue_depth": self._get_queue(t).qsize()} for t in teams}

    def clear(self, team: str | None = None) -> None:
        """Drain queue(s) — primarily for testing."""
        if team:
            q = self._get_queue(team)
            while not q.empty():
                try:
                    q.get_nowait()
                except queue.Empty:
                    break
        else:
            with self._lock:
                for q in self._queues.values():
                    while not q.empty():
                        try:
                            q.get_nowait()
                        except queue.Empty:
                            break


# Process-level singleton
_bus = MessageBus()


def get_bus() -> MessageBus:
    """Return the process-level singleton MessageBus."""
    return _bus
