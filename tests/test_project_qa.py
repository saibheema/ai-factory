from factory.pipeline.project_qa import answer_project_question


def test_answer_project_question_with_matches() -> None:
    snapshot = {
        "team-backend_eng": [
            "proj-qa:Processed by backend_eng artifact_lines=4 API contract for mapping",
            "other:irrelevant",
        ],
        "team-qa_eng": [
            "proj-qa:QA checks for mapping and acceptance criteria",
        ],
    }

    answer, matches = answer_project_question(
        project_id="proj-qa",
        question="What is API mapping contract?",
        memory_snapshot=snapshot,
    )

    assert "Most relevant project memory sources" in answer
    assert len(matches) >= 1
    assert matches[0].bank_id.startswith("team-")


def test_answer_project_question_no_matches() -> None:
    answer, matches = answer_project_question(
        project_id="missing-proj",
        question="status?",
        memory_snapshot={"team-a": ["proj-1:abc"]},
    )
    assert "No strong memory match" in answer
    assert matches == []
