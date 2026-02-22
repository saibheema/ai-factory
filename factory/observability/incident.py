import os
from typing import Any

import httpx


class IncidentNotifier:
    """Best-effort incident delivery to common sinks.

    Supported channels:
    - Generic webhook via INCIDENT_WEBHOOK_URL
    - Slack incoming webhook via SLACK_WEBHOOK_URL
    - PagerDuty Events API v2 via PAGERDUTY_ROUTING_KEY
    """

    def __init__(self) -> None:
        self.incident_webhook_url = os.getenv("INCIDENT_WEBHOOK_URL", "").strip()
        self.slack_webhook_url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
        self.pagerduty_routing_key = os.getenv("PAGERDUTY_ROUTING_KEY", "").strip()

    def config_snapshot(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.incident_webhook_url or self.slack_webhook_url or self.pagerduty_routing_key),
            "incident_webhook": bool(self.incident_webhook_url),
            "slack": bool(self.slack_webhook_url),
            "pagerduty": bool(self.pagerduty_routing_key),
        }

    def notify(self, title: str, severity: str, payload: dict[str, Any]) -> dict[str, Any]:
        channels: list[str] = []

        if self.incident_webhook_url:
            self._post_generic_webhook(title=title, severity=severity, payload=payload)
            channels.append("incident_webhook")

        if self.slack_webhook_url:
            self._post_slack(title=title, severity=severity, payload=payload)
            channels.append("slack")

        if self.pagerduty_routing_key:
            self._post_pagerduty(title=title, severity=severity, payload=payload)
            channels.append("pagerduty")

        return {
            "delivered": bool(channels),
            "channels": channels,
            "title": title,
            "severity": severity,
        }

    def _post_generic_webhook(self, title: str, severity: str, payload: dict[str, Any]) -> None:
        body = {"title": title, "severity": severity, "payload": payload}
        with httpx.Client(timeout=10.0) as client:
            response = client.post(self.incident_webhook_url, json=body)
            response.raise_for_status()

    def _post_slack(self, title: str, severity: str, payload: dict[str, Any]) -> None:
        text = f"[{severity.upper()}] {title}\n{payload}"
        with httpx.Client(timeout=10.0) as client:
            response = client.post(self.slack_webhook_url, json={"text": text})
            response.raise_for_status()

    def _post_pagerduty(self, title: str, severity: str, payload: dict[str, Any]) -> None:
        body = {
            "routing_key": self.pagerduty_routing_key,
            "event_action": "trigger",
            "payload": {
                "summary": title,
                "severity": severity if severity in {"info", "warning", "error", "critical"} else "warning",
                "source": "ai-factory-orchestrator",
                "custom_details": payload,
            },
        }
        with httpx.Client(timeout=10.0) as client:
            response = client.post("https://events.pagerduty.com/v2/enqueue", json=body)
            response.raise_for_status()
