from fastapi.testclient import TestClient
import time

from services.orchestrator.app.main import app


client = TestClient(app)


def test_full_teams_endpoint() -> None:
    r = client.get('/api/pipelines/full/teams')
    assert r.status_code == 200
    payload = r.json()
    assert payload['phase'] == 2
    assert len(payload['teams']) == 17


def test_full_teams_endpoint_alias() -> None:
    r = client.get('/api/pipelines/phase2/teams')
    assert r.status_code == 200
    payload = r.json()
    assert len(payload['teams']) == 17


def test_full_run_endpoint() -> None:
    r = client.post('/api/pipelines/full/run', json={'project_id': 'p2-1', 'requirement': 'expand teams'})
    assert r.status_code == 200
    payload = r.json()
    assert payload['phase'] == 2
    assert len(payload['stages']) == 17
    assert len(payload['artifacts']) == 17
    assert 'handoff_to:' in payload['artifacts']['product_mgmt']
    assert len(payload['handoffs']) == 17
    assert payload['overall_handoff_ok'] is True
    assert 'governance' in payload
    assert isinstance(payload['governance'], dict)


def test_full_run_endpoint_alias() -> None:
    r = client.post('/api/pipelines/phase2/run', json={'project_id': 'full-1', 'requirement': 'execute full pipeline'})
    assert r.status_code == 200
    payload = r.json()
    assert payload['phase'] == 2
    assert payload['overall_handoff_ok'] is True


def test_full_e2e_endpoint() -> None:
    r = client.get('/api/pipelines/full/e2e')
    assert r.status_code == 200
    payload = r.json()
    assert payload['project_id'] == 'phase2-e2e'
    assert payload['overall_handoff_ok'] is True


def test_full_e2e_endpoint_alias() -> None:
    r = client.get('/api/pipelines/phase2/e2e')
    assert r.status_code == 200
    payload = r.json()
    assert payload['overall_handoff_ok'] is True


def test_governance_budgets_endpoint() -> None:
    r = client.get('/api/governance/budgets')
    assert r.status_code == 200
    payload = r.json()
    assert 'enabled' in payload
    assert 'teams' in payload


def test_update_team_governance_endpoint() -> None:
    r = client.put('/api/governance/teams/backend_eng', json={'model': 'factory/coder', 'budget_usd': 1.25})
    assert r.status_code == 200
    payload = r.json()
    assert payload['status'] == 'updated'
    assert payload['team'] == 'backend_eng'
    assert payload['model'] == 'factory/coder'
    assert payload['limit_usd'] == 1.25


def test_update_team_governance_invalid_model_rejected() -> None:
    r = client.put('/api/governance/teams/backend_eng', json={'model': 'unknown/model'})
    assert r.status_code == 400


def test_incident_config_endpoint() -> None:
    r = client.get('/api/observability/incidents/config')
    assert r.status_code == 200
    payload = r.json()
    assert 'enabled' in payload
    assert 'slack' in payload
    assert 'pagerduty' in payload


def test_full_run_async_task_tracking_endpoint() -> None:
    start = client.post('/api/pipelines/full/run/async', json={'project_id': 'track-1', 'requirement': 'track full run'})
    assert start.status_code == 200
    task_id = start.json()['task_id']

    payload = None
    for _ in range(30):
        status = client.get(f'/api/tasks/{task_id}')
        assert status.status_code == 200
        payload = status.json()
        assert payload['status'] in {'running', 'completed', 'failed'}
        assert isinstance(payload['activities'], list)
        if payload['status'] == 'completed':
            break
        time.sleep(0.05)

    assert payload is not None
    assert payload['status'] == 'completed'
    assert len(payload['activities']) == 17
    assert payload['result']['overall_handoff_ok'] is True


def test_full_run_async_solution_arch_only_override() -> None:
    start = client.post(
        '/api/pipelines/full/run/async',
        json={
            'project_id': 'sa-only-1',
            'requirement': 'create a kids calculator',
            'teams': ['solution_arch'],
        },
    )
    assert start.status_code == 200
    task_id = start.json()['task_id']

    payload = None
    for _ in range(40):
        status = client.get(f'/api/tasks/{task_id}')
        assert status.status_code == 200
        payload = status.json()
        assert payload['status'] in {'running', 'completed', 'failed'}
        if payload['status'] in {'completed', 'failed'}:
            break
        time.sleep(0.05)

    assert payload is not None
    assert payload['status'] == 'completed'
    assert len(payload['activities']) == 1
    assert payload['activities'][0]['team'] == 'solution_arch'
