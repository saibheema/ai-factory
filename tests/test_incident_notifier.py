from factory.observability.incident import IncidentNotifier


def test_incident_notifier_config_snapshot_without_env() -> None:
    notifier = IncidentNotifier()
    snapshot = notifier.config_snapshot()
    assert "enabled" in snapshot
    assert "slack" in snapshot
    assert "pagerduty" in snapshot


def test_incident_notifier_notify_no_channels() -> None:
    notifier = IncidentNotifier()
    result = notifier.notify(title="t", severity="warning", payload={"k": "v"})
    assert result["delivered"] is False
    assert result["channels"] == []
