from factory.memory.memory_controller import MemoryController
from factory.pipeline.phase2_pipeline import Phase2Context, Phase2Pipeline


class LocalAdapter:
    def __init__(self) -> None:
        self._m = MemoryController()

    def recall(self, bank_id: str, limit: int = 5):
        return self._m.recall(bank_id, limit)

    def retain(self, bank_id: str, item: str):
        self._m.retain(bank_id, item)

    def snapshot(self):
        return self._m.snapshot()


def test_phase2_pipeline_runs_17_teams() -> None:
    pipeline = Phase2Pipeline(memory=LocalAdapter())
    run = pipeline.run(Phase2Context(project_id="p2", requirement="start phase2"))

    assert len(run.results) == 17
    assert all(r.status == "COMPLETE" for r in run.results)
    assert len(run.artifacts) == 17
    assert len(run.handoffs) == 17
    assert run.overall_handoff_ok is True
    assert all(h["ok"] for h in run.handoffs)


def test_phase2_pipeline_handoff_contract_order() -> None:
    pipeline = Phase2Pipeline(memory=LocalAdapter())
    run = pipeline.run(Phase2Context(project_id="p2-handoff", requirement="validate sequence"))

    expected = pipeline.teams
    observed_teams = [h["team"] for h in run.handoffs]
    assert observed_teams == expected

    for idx, handoff in enumerate(run.handoffs):
        expected_next = expected[idx + 1] if idx < len(expected) - 1 else "none"
        assert handoff["expected_handoff_to"] == expected_next
        assert handoff["observed_handoff_to"] == expected_next
        assert handoff["ok"] is True
