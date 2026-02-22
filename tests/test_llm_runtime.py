from factory.llm.runtime import TeamLLMRuntime


def test_runtime_governance_has_available_models() -> None:
    rt = TeamLLMRuntime()
    snap = rt.governance_snapshot()
    assert "available_models" in snap
    assert "factory/coder" in snap["available_models"]


def test_runtime_update_team_config() -> None:
    rt = TeamLLMRuntime()
    updated = rt.update_team_config(team="backend_eng", model="factory/coder", budget_usd=1.1)
    assert updated["team"] == "backend_eng"
    assert updated["model"] == "factory/coder"
    assert updated["limit_usd"] == 1.1


def test_runtime_update_team_config_rejects_invalid_model() -> None:
    rt = TeamLLMRuntime()
    # Models without provider/model format should be rejected
    try:
        rt.update_team_config(team="backend_eng", model="invalid_no_slash")
        assert False, "expected ValueError"
    except ValueError:
        assert True
    # Models with provider/model format (like openai/gpt-4o) should be accepted
    updated = rt.update_team_config(team="backend_eng", model="openai/gpt-4o")
    assert updated["model"] == "openai/gpt-4o"


def test_runtime_update_team_api_key() -> None:
    rt = TeamLLMRuntime()
    updated = rt.update_team_config(team="backend_eng", api_key="sk-test-1234567890abcdef")
    assert updated["has_custom_key"] is True
    snap = rt.governance_snapshot()
    assert snap["teams"]["backend_eng"]["has_custom_key"] is True
    assert snap["teams"]["backend_eng"]["api_key"].startswith("sk-t")
    assert snap["teams"]["backend_eng"]["api_key"].endswith("cdef")


def test_runtime_clear_api_key() -> None:
    rt = TeamLLMRuntime()
    rt.update_team_config(team="backend_eng", api_key="sk-test-1234567890abcdef")
    rt.update_team_config(team="backend_eng", api_key="")
    snap = rt.governance_snapshot()
    assert snap["teams"]["backend_eng"]["has_custom_key"] is False
