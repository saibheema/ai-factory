from factory.agents.task_result import TaskResult, validate_task_result


def test_task_result_complete_is_valid() -> None:
    result = TaskResult(team="qa_eng", objective="test", status="COMPLETE")
    ok, _ = validate_task_result(result)
    assert ok is True


def test_task_result_needs_clarification_requires_question() -> None:
    result = TaskResult(
        team="backend_eng",
        objective="build",
        status="NEEDS_CLARIFICATION",
        clarification_needed="Need API auth spec",
    )
    ok, _ = validate_task_result(result)
    assert ok is True
