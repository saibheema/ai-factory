from factory.agents.phase2_handlers import _gen_solution_arch, extract_handoff_to, run_phase2_handler


def test_phase2_handler_contains_handoff() -> None:
    stage = run_phase2_handler(team="product_mgmt", requirement="r", prior_count=0)
    assert "handoff_to:" in stage.artifact
    assert extract_handoff_to(stage.artifact) == "biz_analysis"


def test_extract_handoff_unknown_when_missing() -> None:
    assert extract_handoff_to("no handoff line") == "unknown"


def test_next_team_override_replaces_canonical_handoff() -> None:
    """When next_team is supplied, the artifact must use it — not the canonical value.

    This is the core fix for the handoff-mismatch bug: smart routing may skip
    canonical successors (e.g. solution_arch → api_design is canonical, but when
    api_design is not selected, the actual next team might be backend_eng).
    """
    stage = run_phase2_handler(
        team="solution_arch",
        requirement="build a REST API",
        prior_count=0,
        next_team="backend_eng",
    )
    assert "handoff_to:" in stage.artifact
    assert extract_handoff_to(stage.artifact) == "backend_eng"


def test_handoff_ok_for_subset_of_teams() -> None:
    """Simulate a smart-routed 3-team run and verify all handoffs match."""
    selected = ["solution_arch", "backend_eng", "qa_eng"]

    artifacts = {}
    for idx, team in enumerate(selected):
        nt = selected[idx + 1] if idx + 1 < len(selected) else "none"
        stage = run_phase2_handler(
            team=team,
            requirement="build an API",
            prior_count=0,
            next_team=nt,
        )
        artifacts[team] = stage.artifact

    for idx, team in enumerate(selected):
        expected = selected[idx + 1] if idx + 1 < len(selected) else "none"
        observed = extract_handoff_to(artifacts[team])
        assert observed == expected, (
            f"{team}: expected handoff_to={expected!r} but got {observed!r}"
        )


def test_solution_arch_generator_includes_clarity_questions() -> None:
    llm = (
        "KNOWN INPUTS:\n"
        "- web MVP\n"
        "ASSUMPTIONS:\n"
        "- school-managed deployment\n"
        "OPEN QUESTIONS FOR USER:\n"
        "- Which locales are required at launch?\n"
        "- Should analytics be opt-in by parent?\n"
    )
    gen = _gen_solution_arch("create a kids calculator", llm)
    doc = gen.get("doc_content", "")
    assert "Open Questions for User" in doc
    assert "Requirement Clarity (User in Loop)" in doc
    assert "- Which locales are required at launch?" in doc
    assert "- Should analytics be opt-in by parent?" in doc


def test_solution_arch_stage_artifact_surfaces_clarifying_questions() -> None:
    stage = run_phase2_handler(team="solution_arch", requirement="kids calculator", prior_count=0)
    # Without LLM-provided OPEN QUESTIONS section, no synthetic questions are added.
    assert "clarifying_questions_count:" not in stage.artifact
    assert "clarifying_questions:" not in stage.artifact


def test_solution_arch_followup_with_user_clarifications_has_no_fallback_questions() -> None:
    req = (
        "Original Requirement:\nKids calculator\n\n"
        "User Clarifications (answer to Sol Arch questions):\n"
        "Web-first MVP, basic arithmetic only, COPPA controls enabled."
    )
    stage = run_phase2_handler(team="solution_arch", requirement=req, prior_count=0)
    assert "clarifying_questions_count:" not in stage.artifact


def test_solution_arch_generator_extracts_question_list_field() -> None:
    llm = (
        "OPEN QUESTIONS FOR USER:\n"
        "- Q1?\n"
        "- Q2?\n"
    )
    gen = _gen_solution_arch("r", llm)
    assert gen.get("clarifying_questions") == ["Q1?", "Q2?"]
