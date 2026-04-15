from pathlib import Path

from clawsocialarena.agents.llm_client import MockLLMClient
from clawsocialarena.runtime.runner import ScenarioRunner, RunResult
from clawsocialarena.scenario.loader import ScenarioLoader
from clawsocialarena.types import AuditCondition

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "scenarios"


async def test_run_cu_scheduling_mvp(tmp_path: Path):
    loader = ScenarioLoader(root=FIXTURES)
    scenario, gt = loader.load("cu_scheduling_mvp")

    def make_llm(agent_id: str) -> MockLLMClient:
        if agent_id == "alice":
            return MockLLMClient(
                canned_responses=[
                    "How about Tuesday at 2pm?",
                    "[READY_TO_PIN 2026-04-21T14:00:00Z]",
                ]
            )
        return MockLLMClient(canned_responses=["[READY_TO_PIN 2026-04-21T14:00:00Z]"])

    # Use PASSIVE so the MVP integration test still exercises the ActionLog
    # hash-chaining path. BASELINE now intentionally has no audit infrastructure
    # (spec §5.1 — see Task 3.5a).
    runner = ScenarioRunner(
        scenario=scenario,
        gt=gt,
        llm_factory=make_llm,
        db_path=tmp_path / "run.db",
        condition=AuditCondition.PASSIVE,
    )
    result: RunResult = await runner.run()

    # Strengthened assertions for Phase 1.5
    assert result.turns_used > 0
    assert result.log_rows > 0
    assert result.terminal_predicate_passed is True
    assert result.final_state["pinned_slot"] == "2026-04-21T14:00:00Z"

    # The opening message must appear in the action log (Phase 1.5b fix).
    rows = runner.log.read_all()
    opener_rows = [
        r
        for r in rows
        if r.agent_id == scenario.opening_message["from"]
        and r.payload.get("recipient_id") == scenario.opening_message["to"]
        and r.payload.get("content") == scenario.opening_message["content"]
    ]
    assert len(opener_rows) == 1, "Opening message must appear in action log exactly once"

    # Phase 1.5d: hash chains for every agent must verify
    for agent_spec in scenario.agents:
        assert runner.log.verify_chain(agent_spec.agent_id) is True, (
            f"hash chain for {agent_spec.agent_id} failed verification"
        )
