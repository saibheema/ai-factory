from typing import Literal

from pydantic import BaseModel, Field


class TaskResult(BaseModel):
    team: str
    objective: str
    status: Literal["COMPLETE", "NEEDS_CLARIFICATION", "BLOCKED"]
    reasoning: str = ""
    blockers: list[str] = Field(default_factory=list)
    assumptions_made: list[str] = Field(default_factory=list)
    verified_facts: list[str] = Field(default_factory=list)
    clarification_needed: str | None = None


def validate_task_result(result: TaskResult) -> tuple[bool, str]:
    if result.status == "COMPLETE":
        return True, "ok"
    if result.status == "NEEDS_CLARIFICATION" and result.clarification_needed:
        return True, "clarification-required"
    if result.status == "BLOCKED" and result.blockers:
        return True, "blocked"
    return False, "invalid-task-result-shape"
