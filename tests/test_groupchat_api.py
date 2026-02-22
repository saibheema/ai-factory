from fastapi.testclient import TestClient

from services.groupchat.app.main import app


client = TestClient(app)


def test_groupchat_health() -> None:
    r = client.get('/health')
    assert r.status_code == 200
    assert r.json()['service'] == 'groupchat'


def test_groupchat_plan_session() -> None:
    r = client.post('/session/plan', json={'topic': 'phase2 kickoff', 'participants': ['backend_eng', 'qa_eng']})
    assert r.status_code == 200
    payload = r.json()
    assert payload['topic'] == 'phase2 kickoff'
    assert len(payload['plan']) == 4
