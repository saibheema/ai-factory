from factory.agents.phase2_handlers import extract_handoff_to, run_phase2_handler


def test_phase2_handler_contains_handoff() -> None:
    stage = run_phase2_handler(team="product_mgmt", requirement="r", prior_count=0)
    assert "handoff_to:" in stage.artifact
    assert extract_handoff_to(stage.artifact) == "biz_analysis"


def test_extract_handoff_unknown_when_missing() -> None:
    assert extract_handoff_to("no handoff line") == "unknown"
