from dataclasses import dataclass

from factory.agents.phase1_operatives import (
    backend_eng_operative,
    biz_analysis_operative,
    docs_team_operative,
    qa_eng_operative,
    solution_arch_operative,
)
from factory.agents.task_result import TaskResult
from factory.memory.memory_controller import MemoryController


@dataclass
class Phase1Context:
    project_id: str
    requirement: str


@dataclass
class Phase1RunOutput:
    results: list[TaskResult]
    artifacts: dict[str, str]


class Phase1Pipeline:
    teams = [
        "biz_analysis",
        "solution_arch",
        "backend_eng",
        "qa_eng",
        "docs_team",
    ]

    def __init__(self, memory: MemoryController) -> None:
        self.memory = memory

    def run(self, ctx: Phase1Context) -> Phase1RunOutput:
        outputs: list[TaskResult] = []
        artifacts: dict[str, str] = {}

        ba = biz_analysis_operative(ctx.requirement)
        artifacts[ba.team] = ba.artifact

        arch = solution_arch_operative(ctx.requirement, ba.artifact)
        artifacts[arch.team] = arch.artifact

        be = backend_eng_operative(ctx.requirement, arch.artifact)
        artifacts[be.team] = be.artifact

        qa = qa_eng_operative(be.artifact)
        artifacts[qa.team] = qa.artifact

        docs = docs_team_operative(ctx.requirement, qa.artifact)
        artifacts[docs.team] = docs.artifact

        for team in self.teams:
            bank_id = f"team-{team}"
            recalled = self.memory.recall(bank_id)
            artifact = artifacts.get(team, "")
            summary = f"Processed by {team}. prior={len(recalled)} artifact_lines={len(artifact.splitlines())}"
            self.memory.retain(bank_id, f"{ctx.project_id}:{summary}:{artifact[:120]}")
            outputs.append(
                TaskResult(
                    team=team,
                    objective=ctx.requirement,
                    status="COMPLETE",
                    reasoning=summary,
                    verified_facts=["phase1-operative", f"artifact:{team}"],
                )
            )
        return Phase1RunOutput(results=outputs, artifacts=artifacts)
