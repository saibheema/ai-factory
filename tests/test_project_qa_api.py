from fastapi.testclient import TestClient

from services.orchestrator.app.main import app


client = TestClient(app)


def test_project_qa_endpoint_returns_matches_after_phase1_run() -> None:
    run = client.post(
        "/api/pipelines/core/run",
        json={"project_id": "qa-demo", "requirement": "Create simple PDF mapping MVP"},
    )
    assert run.status_code == 200

    qa = client.post(
        "/api/projects/qa-demo/qa",
        json={"question": "What API contract was generated?"},
    )
    assert qa.status_code == 200
    payload = qa.json()
    assert payload["project_id"] == "qa-demo"
    assert "answer" in payload
    assert isinstance(payload["matches"], list)


def test_project_memory_map_endpoint() -> None:
    run = client.post(
        "/api/pipelines/full/run",
        json={"project_id": "map-demo", "requirement": "Build memory map sample"},
    )
    assert run.status_code == 200

    mm = client.get("/api/projects/map-demo/memory-map")
    assert mm.status_code == 200
    payload = mm.json()
    assert payload["project_id"] == "map-demo"
    assert isinstance(payload["nodes"], list)
    assert isinstance(payload["edges"], list)
    assert "summary" in payload


def test_project_chat_endpoint() -> None:
    run = client.post(
        "/api/pipelines/core/run",
        json={"project_id": "chat-demo", "requirement": "Create chat context"},
    )
    assert run.status_code == 200

    chat = client.post(
        "/api/projects/chat-demo/chat",
        json={"message": "What was produced in backend stage?"},
    )
    assert chat.status_code == 200
    payload = chat.json()
    assert payload["project_id"] == "chat-demo"
    assert "answer" in payload
    assert isinstance(payload["matches"], list)


def test_project_group_chat_endpoint() -> None:
    run = client.post(
        "/api/pipelines/full/run",
        json={"project_id": "group-demo", "requirement": "Create group chat context"},
    )
    assert run.status_code == 200

    gc = client.post(
        "/api/projects/group-demo/group-chat",
        json={"topic": "Release readiness", "participants": ["backend_eng", "qa_eng", "docs_team"]},
    )
    assert gc.status_code == 200
    payload = gc.json()
    assert payload["project_id"] == "group-demo"
    assert len(payload["participants"]) == 3
    assert isinstance(payload["plan"], list)
    assert isinstance(payload["updates"], list)
