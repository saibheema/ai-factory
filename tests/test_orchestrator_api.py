from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from services.orchestrator.app.main import app, broker


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_metrics_endpoint() -> None:
    client.post(
        "/api/pipelines/core/run",
        json={"project_id": "metrics-core", "requirement": "metrics core flow"},
    )
    client.post(
        "/api/pipelines/full/run",
        json={"project_id": "metrics-full", "requirement": "metrics full flow"},
    )
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "ai_factory_metrics_scrapes_total" in response.text
    assert "ai_factory_core_pipeline_runs_total" in response.text
    assert "ai_factory_full_pipeline_runs_total" in response.text


def test_run_core_pipeline() -> None:
    response = client.post(
        "/api/pipelines/core/run",
        json={"project_id": "proj-1", "requirement": "build phase1"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == "proj-1"
    assert len(payload["stages"]) == 5
    assert len(payload["artifacts"]) == 5


def test_run_core_pipeline_alias() -> None:
    response = client.post(
        "/api/pipelines/phase1/run",
        json={"project_id": "core-1", "requirement": "build core"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] == 1
    assert len(payload["stages"]) == 5


def test_run_core_pipeline_example() -> None:
    response = client.get("/api/pipelines/core/example")
    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] == 1
    assert payload["project_id"] == "example-phase1"
    assert "BRD:" in payload["artifacts"]["biz_analysis"]


def test_run_core_pipeline_example_alias() -> None:
    response = client.get("/api/pipelines/phase1/example")
    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] == 1


def test_clarification_self_routing_rejected() -> None:
    response = client.post(
        "/api/projects/proj-1/ask",
        json={"from_team": "qa_eng", "to_team": "qa_eng", "question": "same team?"},
    )
    assert response.status_code == 400


def test_invalid_clarification_payload_rejected() -> None:
    response = client.post(
        "/api/projects/proj-1/ask",
        json={"from_team": "qa", "to_team": "be", "question": "no"},
    )
    assert response.status_code == 422


def test_clarification_timeout() -> None:
    create = client.post(
        "/api/projects/proj-1/ask",
        json={"from_team": "backend_eng", "to_team": "qa_eng", "question": "Need confirmation details"},
    )
    assert create.status_code == 200
    request_id = create.json()["request_id"]

    broker._requests[request_id].expires_at = datetime.now(UTC) - timedelta(seconds=1)

    get_response = client.get(f"/api/clarifications/{request_id}")
    assert get_response.status_code == 200
    assert get_response.json()["answer"] == "TIMEOUT"


def test_clarification_respond_roundtrip() -> None:
    create = client.post(
        "/api/projects/proj-1/ask",
        json={"from_team": "backend_eng", "to_team": "qa_eng", "question": "Need QA signoff format"},
    )
    request_id = create.json()["request_id"]

    respond = client.post(
        f"/api/clarifications/{request_id}/respond",
        json={"answer": "Use phase-1 template"},
    )
    assert respond.status_code == 200

    get_response = client.get(f"/api/clarifications/{request_id}")
    assert get_response.status_code == 200
    assert "phase-1 template" in (get_response.json()["answer"] or "")
