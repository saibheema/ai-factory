import concurrent.futures
import logging
from dataclasses import dataclass

from factory.agents.phase2_handlers import extract_handoff_to, run_phase2_handler
from factory.agents.task_result import TaskResult
from factory.llm.runtime import TeamLLMRuntime
from factory.memory.memory_controller import RemoteMemoryController

log = logging.getLogger(__name__)

# Teams that can run in parallel within each wave.
# Wave N completes before Wave N+1 starts, preserving dependency order while
# maximising throughput across independent teams.
EXECUTION_WAVES: list[list[str]] = [
    ["product_mgmt", "biz_analysis"],
    ["solution_arch", "api_design", "ux_ui"],
    ["frontend_eng", "backend_eng", "database_eng", "data_eng", "ml_eng"],
    ["security_eng", "compliance", "devops"],
    ["qa_eng", "sre_ops"],
    ["docs_team", "feature_eng"],
]


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
        """Execute teams in dependency waves (parallel within each wave)."""
        outputs: list[TaskResult] = []
        artifacts: dict[str, str] = {}

        def _run_team(team: str) -> tuple[str, object]:
            bank_id = f"team-{team}"
            prior = self.memory.recall(bank_id=bank_id, limit=3)
            stage = run_phase2_handler(
                team=team,
                requirement=ctx.requirement,
                prior_count=len(prior),
                llm_runtime=self.llm_runtime,
            )
            summary = f"phase2-stage={team} prior={len(prior)} artifact_lines={len(stage.artifact.splitlines())}"
            self.memory.retain(bank_id=bank_id, item=f"{ctx.project_id}:{summary}:{stage.artifact[:120]}")
            return team, stage

        # Execute each wave; teams within a wave run in parallel
        for wave in EXECUTION_WAVES:
            wave_teams = [t for t in wave if t in self.teams]
            if not wave_teams:
                continue
            max_workers = min(len(wave_teams), 5)  # cap to avoid rate-limit bursts
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(_run_team, t): t for t in wave_teams}
                for fut in concurrent.futures.as_completed(futures):
                    try:
                        team, stage = fut.result()
                    except Exception as exc:
                        team = futures[fut]
                        log.warning("Phase2 wave team %s failed: %s", team, exc)
                        # Create a minimal fallback artifact so the pipeline continues
                        from factory.agents.phase2_handlers import Phase2StageArtifact
                        stage = Phase2StageArtifact(
                            team=team,
                            artifact=f"P2:{team}\n- requirement: {ctx.requirement}\n- action: fallback (error: {exc})\n- handoff_to: none",
                        )
                    artifacts[team] = stage.artifact
                    summary = f"phase2-stage={team} artifact_lines={len(stage.artifact.splitlines())}"
                    outputs.append(
                        TaskResult(
                            team=team,
                            objective=ctx.requirement,
                            status="COMPLETE",
                            reasoning=summary,
                            verified_facts=["phase2-kickoff", f"artifact:{team}"],
                        )
                    )

        # Sort outputs to match the canonical team ordering
        team_order = {t: i for i, t in enumerate(self.teams)}
        outputs.sort(key=lambda r: team_order.get(r.team, 999))

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
