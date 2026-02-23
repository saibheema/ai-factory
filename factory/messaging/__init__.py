"""factory.messaging — Agent-to-Agent (A2A) messaging module.

Provides an in-process publish/subscribe message bus for inter-team
communication, plus actor-style ``[@team: message]`` pattern dispatch.

Usage
-----
    from factory.messaging import send, receive, dispatch_actor_messages

    # Send a direct message
    send(to_team="backend_eng", from_team="api_design", content="Please scaffold the REST endpoint")

    # Parse and dispatch [@team: msg] patterns found in LLM output
    ids = dispatch_actor_messages(llm_output, from_team="solution_arch")

    # Receive next message for a team (non-blocking)
    msg = receive(team="backend_eng")
"""
from factory.messaging.bus import MessageBus, Message, get_bus
from factory.messaging.actor import (
    send,
    receive,
    peek_inbox,
    dispatch_actor_messages,
    parse_actor_messages,
)

__all__ = [
    "MessageBus",
    "Message",
    "get_bus",
    "send",
    "receive",
    "peek_inbox",
    "dispatch_actor_messages",
    "parse_actor_messages",
]
