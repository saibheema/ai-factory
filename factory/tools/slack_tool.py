"""Slack tool — send messages, post rich blocks, and upload files to Slack.

Used by all teams for human-readable pipeline notifications, alerts,
and cross-team communication beyond ntfy.

Env vars:
  SLACK_BOT_TOKEN  — Slack Bot OAuth token (xoxb-...)
  SLACK_CHANNEL    — default channel (default: #ai-factory)
  SLACK_USERNAME   — bot display name (default: AI Factory)
"""

import logging
import os

import httpx

log = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
DEFAULT_CHANNEL = os.getenv("SLACK_CHANNEL", "#ai-factory")
BOT_USERNAME = os.getenv("SLACK_USERNAME", "AI Factory")
SLACK_API = "https://slack.com/api"


def _post(endpoint: str, payload: dict) -> dict:
    if not BOT_TOKEN:
        log.debug("SLACK_BOT_TOKEN not set — Slack call skipped")
        return {"ok": False, "error": "SLACK_BOT_TOKEN not set"}
    try:
        resp = httpx.post(
            f"{SLACK_API}/{endpoint}",
            headers={"Authorization": f"Bearer {BOT_TOKEN}", "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        data = resp.json()
        if not data.get("ok"):
            log.warning("Slack %s error: %s", endpoint, data.get("error"))
        return data
    except Exception as e:
        log.warning("Slack call failed: %s", e)
        return {"ok": False, "error": str(e)}


def send_message(text: str, channel: str = "", thread_ts: str = "") -> dict:
    """Send a plain-text message to a Slack channel.

    Returns:
      {"ok": bool, "ts": str (message timestamp), "error": str|None}
    """
    payload: dict = {
        "channel": channel or DEFAULT_CHANNEL,
        "text": text,
        "username": BOT_USERNAME,
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts
    return _post("chat.postMessage", payload)


def send_blocks(blocks: list[dict], text: str = "", channel: str = "") -> dict:
    """Send a rich Block Kit message.

    Args:
      blocks: Slack Block Kit blocks list
      text:   Fallback text for notifications
    """
    payload = {
        "channel": channel or DEFAULT_CHANNEL,
        "text": text or "AI Factory update",
        "blocks": blocks,
        "username": BOT_USERNAME,
    }
    return _post("chat.postMessage", payload)


def send_stage_complete(
    team: str,
    project_id: str,
    artifact_title: str,
    handoff_to: str,
    channel: str = "",
) -> dict:
    """Send a formatted stage-complete notification to Slack.

    Returns:
      {"ok": bool, "ts": str}
    """
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"✅ {team.replace('_', ' ').title()} — Stage Complete"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Project:*\n{project_id}"},
                {"type": "mrkdwn", "text": f"*Artifact:*\n{artifact_title}"},
                {"type": "mrkdwn", "text": f"*Handoff to:*\n{handoff_to}"},
                {"type": "mrkdwn", "text": f"*Team:*\n{team}"},
            ],
        },
        {"type": "divider"},
    ]
    return send_blocks(blocks, text=f"[{team}] Stage complete → {handoff_to}", channel=channel)


def send_alert(title: str, message: str, severity: str = "warning", channel: str = "") -> dict:
    """Send an alert message with colour-coded attachment.

    severity: "info" | "warning" | "critical"
    """
    color_map = {"info": "#36a64f", "warning": "#ff9400", "critical": "#ff0000"}
    color = color_map.get(severity, "#cccccc")
    payload = {
        "channel": channel or DEFAULT_CHANNEL,
        "username": BOT_USERNAME,
        "attachments": [
            {
                "color": color,
                "title": f"[{severity.upper()}] {title}",
                "text": message,
                "footer": "AI Factory Alerting",
            }
        ],
    }
    return _post("chat.postMessage", payload)


def upload_file(
    content: str,
    filename: str,
    title: str = "",
    channel: str = "",
    filetype: str = "text",
) -> dict:
    """Upload a text file snippet to Slack.

    Returns:
      {"ok": bool, "file": dict}
    """
    if not BOT_TOKEN:
        return {"ok": False, "error": "SLACK_BOT_TOKEN not set"}
    try:
        resp = httpx.post(
            f"{SLACK_API}/files.upload",
            headers={"Authorization": f"Bearer {BOT_TOKEN}"},
            data={
                "channels": channel or DEFAULT_CHANNEL,
                "content": content,
                "filename": filename,
                "title": title or filename,
                "filetype": filetype,
            },
            timeout=30,
        )
        return resp.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def create_channel(name: str) -> dict:
    """Create a Slack channel (returns existing if already exists)."""
    result = _post("conversations.create", {"name": name})
    if not result.get("ok") and result.get("error") == "name_taken":
        return {"ok": True, "error": None, "already_existed": True}
    return result
