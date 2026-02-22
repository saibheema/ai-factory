from fastapi.testclient import TestClient

from services.memory.app.main import app


client = TestClient(app)


def test_memory_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_memory_retain_and_recall() -> None:
    retain = client.post("/banks/test-bank/retain", json={"item": "hello"})
    assert retain.status_code == 200

    recall = client.get("/banks/test-bank/recall?limit=5")
    assert recall.status_code == 200
    payload = recall.json()
    assert "hello" in payload["items"]
    assert payload["store"] in {"memory", "postgres"}


def test_memory_snapshot() -> None:
    response = client.get("/banks/snapshot")
    assert response.status_code == 200
    assert "banks" in response.json()
