"""Notification tool — send handoff and stage-complete alerts.

Supports:
  - ntfy  (open source self-hosted push notifications)
  - Slack webhook
  - Generic HTTP webhook

Env vars:
  NTFY_URL        — ntfy server URL e.g. https://ntfy.sh  (default: https://ntfy.sh)
  NTFY_TOPIC      — default topic (default: ai-factory)
  SLACK_WEBHOOK_URL — Slack incoming webhook URL
  NOTIFY_WEBHOOK_URL — generic webhook URL (POST with JSON body)
"""

import logging
import os

import httpx

log = logging.getLogger(__name__)

NTFY_URL = os.getenv("NTFY_URL", "https://ntfy.sh")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "ai-factory")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
NOTIFY_WEBHOOK_URL = os.getenv("NOTIFY_WEBHOOK_URL", "")


def notify(
    title: str,
    message: str,
    tags: list[str] | None = None,
    priority: str = "default",  # min | low | default | high | urgent
    topic: str | None = None,
) -> dict:
    """Send a notification via all configured channels.

    Returns: {"channels": [...], "errors": [...]}
    """
    channels, errors = [], []

    # ntfy
    ntfy_result = _ntfy(title, message, tags or [], priority, topic or NTFY_TOPIC)
    if ntfy_result.get("ok"):
        channels.append("ntfy")
    else:
        errors.append(f"ntfy: {ntfy_result.get('error', 'unknown')}")

    # Slack
    if SLACK_WEBHOOK_URL:
        slack_result = _slack(title, message)
        if slack_result.get("ok"):
            channels.append("slack")
        else:
            errors.append(f"slack: {slack_result.get('error', 'unknown')}")

    # Generic webhook
    if NOTIFY_WEBHOOK_URL:
        wh_result = _webhook(title, message, tags or [])
        if wh_result.get("ok"):
            channels.append("webhook")
        else:
            errors.append(f"webhook: {wh_result.get('error', 'unknown')}")

    log.info("notify '%s' → channels=%s errors=%s", title, channels, errors)
    return {"channels": channels, "errors": errors, "delivered": len(channels) > 0}


def notify_team_complete(team: str, project_id: str, next_team: str, summary: str) -> dict:
    """Standard handoff notification when a team completes its SDLC stage."""
    title = f"✅ {team} → {next_team}"
    message = f"[{project_id}] {team} completed. Handing off to {next_team}.\n{summary[:200]}"
    return notify(title=title, message=message, tags=[team, project_id, "handoff"], priority="default")


def notify_error(team: str, project_id: str, error: str) -> dict:
    """Send an error alert."""
    title = f"🔴 {team} FAILED"
    message = f"[{project_id}] {team} hit an error: {error[:300]}"
    return notify(title=title, message=message, tags=[team, "error"], priority="high")


# ── Backends ─────────────────────────────────────────────────────────────────

def _ntfy(title: str, message: str, tags: list[str], priority: str, topic: str) -> dict:
    try:
        resp = httpx.post(
            f"{NTFY_URL}/{topic}",
            content=message.encode(),
            headers={
                "Title": title,
                "Tags": ",".join(tags) if tags else "ai-factory",
                "Priority": priority,
            },
            timeout=10,
        )
        return {"ok": resp.status_code < 300}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _slack(title: str, message: str) -> dict:
    try:
        resp = httpx.post(
            SLACK_WEBHOOK_URL,
            json={"text": f"*{title}*\n{message}"},
            timeout=10,
        )
        return {"ok": resp.status_code == 200}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _webhook(title: str, message: str, tags: list[str]) -> dict:
    try:
        resp = httpx.post(
            NOTIFY_WEBHOOK_URL,
            json={"title": title, "message": message, "tags": tags},
            timeout=10,
        )
        return {"ok": resp.status_code < 300}
    except Exception as e:
        return {"ok": False, "error": str(e)}
