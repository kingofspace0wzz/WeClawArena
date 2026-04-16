from pathlib import Path

from clawsocialarena.agents.llm_client import MockLLMClient
from clawsocialarena.baselines.vanilla_aa import VanillaAAEvalRunner, VanillaAAScorecard
from clawsocialarena.eval.runner import EvalRunner
from clawsocialarena.runtime.runner import ScenarioRunner
from clawsocialarena.scenario.loader import ScenarioLoader
from clawsocialarena.types import AuditCondition

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "scenarios"


async def test_vanilla_aa_produces_scorecard(tmp_path: Path):
    loader = ScenarioLoader(root=FIXTURES)
    scenario, gt = loader.load("cu_scheduling_mvp")

    def factory(aid: str):
        return MockLLMClient(
            canned_responses=["[READY_TO_PIN 2026-04-21T14:00:00Z]"]
        )

    runner = ScenarioRunner(
        scenario=scenario, gt=gt,
        llm_factory=factory, db_path=tmp_path / "run.db",
        condition=AuditCondition.PASSIVE,
    )
    await runner.run()

    card = VanillaAAEvalRunner().evaluate(
        action_log=runner.log, shadow_log=runner.shadow, gt=gt
    )
    assert isinstance(card, VanillaAAScorecard)
    expected = {
        "recoverability",
        "policy_checkability",
        "attribution",
        "evidence_integrity",
        "phase_scoped_policy",
    }
    assert set(card.dims.keys()) == expected
    # Phase-scoped is always 1.0 under vanilla AA
    assert card.dims["phase_scoped_policy"] == 1.0


async def test_vanilla_aa_phase_scoped_always_one(tmp_path: Path):
    """Even with phase-scoped GT policies, vanilla AA reports 1.0 (doesn't evaluate them)."""
    loader = ScenarioLoader(root=FIXTURES)
    scenario, gt = loader.load("cu_scheduling_mvp")
    # Inject a phase-scoped policy into GT
    gt_with_phase = gt.model_copy(update={
        "policies": {
            "flat": [],
            "phase_scoped": [
                {
                    "policy_id": "p1",
                    "phase": "discovery",
                    "kind": "always_false",
                    "params": {},
                    "required_fields": [],
                }
            ],
        }
    })

    def factory(aid):
        return MockLLMClient(canned_responses=["[READY_TO_PIN 2026-04-21T14:00:00Z]"])

    runner = ScenarioRunner(
        scenario=scenario, gt=gt_with_phase,
        llm_factory=factory, db_path=tmp_path / "run.db",
        condition=AuditCondition.PASSIVE,
    )
    await runner.run()

    saf_card = EvalRunner().evaluate(
        action_log=runner.log, shadow_log=runner.shadow, gt=gt_with_phase
    )
    vanilla_card = VanillaAAEvalRunner().evaluate(
        action_log=runner.log, shadow_log=runner.shadow, gt=gt_with_phase
    )
    # SAF fails phase_scoped (predicate always_false fires)
    assert saf_card.saf.dims["phase_scoped_policy"] == 0.0
    # Vanilla AA ignores phase-scoped entirely -> 1.0
    assert vanilla_card.dims["phase_scoped_policy"] == 1.0
    # The overall score diverges: vanilla AA overstates auditability
    assert vanilla_card.overall > saf_card.saf.overall
