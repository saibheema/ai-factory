from factory.memory.memory_controller import MemoryController
from factory.pipeline.phase1_pipeline import Phase1Context, Phase1Pipeline


def test_phase1_pipeline_runs_all_teams() -> None:
    pipeline = Phase1Pipeline(memory=MemoryController())
    run = pipeline.run(Phase1Context(project_id="p1", requirement="ship mvp"))

    assert len(run.results) == 5
    assert all(r.status == "COMPLETE" for r in run.results)
    assert set(run.artifacts.keys()) == {"biz_analysis", "solution_arch", "backend_eng", "qa_eng", "docs_team"}
    assert "BRD:" in run.artifacts["biz_analysis"]
