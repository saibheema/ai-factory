from dataclasses import dataclass

from factory.agents.phase2_handlers import extract_handoff_to, run_phase2_handler
from factory.agents.task_result import TaskResult
from factory.llm.runtime import TeamLLMRuntime
from factory.memory.memory_controller import RemoteMemoryController


@dataclass
class Phase2Context:
    project_id: str
    requirement: str


@dataclass
class Phase2RunOutput:
    results: list[TaskResult]
    artifacts: dict[str, str]
    handoffs: list[dict[str, str | bool]]
    overall_handoff_ok: bool
    governance: dict[str, object]


class Phase2Pipeline:
    teams = [
        "product_mgmt",
        "biz_analysis",
        "solution_arch",
        "api_design",
        "ux_ui",
        "frontend_eng",
        "backend_eng",
        "database_eng",
        "data_eng",
        "ml_eng",
        "security_eng",
        "compliance",
        "devops",
        "qa_eng",
        "sre_ops",
        "docs_team",
        "feature_eng",
    ]

    def __init__(self, memory: RemoteMemoryController, llm_runtime: TeamLLMRuntime | None = None) -> None:
        self.memory = memory
        self.llm_runtime = llm_runtime

    def run(self, ctx: Phase2Context) -> Phase2RunOutput:
        outputs: list[TaskResult] = []
        artifacts: dict[str, str] = {}
        for team in self.teams:
            bank_id = f"team-{team}"
            prior = self.memory.recall(bank_id=bank_id, limit=3)
            stage = run_phase2_handler(
                team=team,
                requirement=ctx.requirement,
                prior_count=len(prior),
                llm_runtime=self.llm_runtime,
            )
            artifacts[team] = stage.artifact
            summary = f"phase2-stage={team} prior={len(prior)} artifact_lines={len(stage.artifact.splitlines())}"
            self.memory.retain(bank_id=bank_id, item=f"{ctx.project_id}:{summary}:{stage.artifact[:120]}")
            outputs.append(
                TaskResult(
                    team=team,
                    objective=ctx.requirement,
                    status="COMPLETE",
                    reasoning=summary,
                    verified_facts=["phase2-kickoff", f"artifact:{team}"],
                )
            )
        handoffs: list[dict[str, str | bool]] = []
        for idx, team in enumerate(self.teams):
            expected = self.teams[idx + 1] if idx < len(self.teams) - 1 else "none"
            observed = extract_handoff_to(artifacts.get(team, ""))
            handoffs.append(
                {
                    "team": team,
                    "expected_handoff_to": expected,
                    "observed_handoff_to": observed,
                    "ok": observed == expected,
                }
            )

        overall_handoff_ok = all(bool(x["ok"]) for x in handoffs)

        return Phase2RunOutput(
            results=outputs,
            artifacts=artifacts,
            handoffs=handoffs,
            overall_handoff_ok=overall_handoff_ok,
            governance=(self.llm_runtime.governance_snapshot() if self.llm_runtime is not None else {"enabled": False}),
        )
