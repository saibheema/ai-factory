"""factory.messaging.actor — Actor-style A2A utilities.

Provides ``[@team: message]`` pattern parsing so that LLM outputs can
contain embedded inter-team messages that are automatically dispatched
onto the message bus.

Example LLM output that would be parsed and dispatched::

    The architecture looks good. [@backend_eng: Please ensure the DB
    connection pool is capped at 20.] [@qa_eng: Add load tests for the
    /search endpoint before we merge.]

Calling ``dispatch_actor_messages(llm_output, from_team="solution_arch")``
would put two messages on the bus — one for backend_eng, one for qa_eng.
"""
from __future__ import annotations

import re
from factory.messaging.bus import get_bus, Message

# Matches [@team_name: message content] — team names use word chars + underscore
_ACTOR_RE = re.compile(r"\[@([\w]+):\s*(.+?)\]", re.DOTALL)


# ── Pattern parsing ────────────────────────────────────────────────────────────


def parse_actor_messages(text: str) -> list[dict]:
    """Return all ``[@team: content]`` mentions found in *text*.

    Returns
    -------
    list[dict]
        Each dict has ``to_team`` and ``content`` keys.
    """
    return [
        {"to_team": team.strip(), "content": content.strip()}
        for team, content in _ACTOR_RE.findall(text)
    ]


# ── Bus wrappers ───────────────────────────────────────────────────────────────


def send(
    to_team: str,
    from_team: str,
    content: str,
    metadata: dict | None = None,
) -> str:
    """Send a direct A2A message. Returns the message ID."""
    return get_bus().send(
        to_team=to_team,
        from_team=from_team,
        content=content,
        metadata=metadata,
    )


def receive(team: str, timeout: float = 0.0) -> Message | None:
    """Receive the next message for *team* (non-blocking by default)."""
    return get_bus().receive(team=team, timeout=timeout)


def peek_inbox(team: str) -> list[Message]:
    """Return a snapshot of pending messages without consuming them."""
    return get_bus().peek(team)


# ── Dispatcher ─────────────────────────────────────────────────────────────────


def dispatch_actor_messages(text: str, from_team: str) -> list[str]:
    """Parse all ``[@team: msg]`` patterns in *text* and send them.

    Parameters
    ----------
    text:
        The LLM output or any string that may contain actor-style mentions.
    from_team:
        The originating team that produced *text*.

    Returns
    -------
    list[str]
        The message IDs of the dispatched messages (may be empty).
    """
    bus = get_bus()
    mentions = parse_actor_messages(text)
    ids: list[str] = []
    for m in mentions:
        mid = bus.send(
            to_team=m["to_team"],
            from_team=from_team,
            content=m["content"],
            metadata={"source": "actor_dispatch", "origin_team": from_team},
        )
        ids.append(mid)
    return ids
