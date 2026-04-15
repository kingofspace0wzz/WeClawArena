import json
from pathlib import Path

from clawsocialarena.agents.llm_client import MockLLMClient
from clawsocialarena.eval.runner import EvalRunner
from clawsocialarena.eval.scorecard import RunScorecard
from clawsocialarena.runtime.runner import ScenarioRunner
from clawsocialarena.scenario.loader import ScenarioLoader
from clawsocialarena.types import AuditCondition

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "scenarios"


async def test_eval_runner_on_mvp(tmp_path: Path):
    loader = ScenarioLoader(root=FIXTURES)
    scenario, gt = loader.load("cu_scheduling_mvp")

    def factory(aid: str):
        if aid == "alice":
            return MockLLMClient(
                canned_responses=[
                    "How about Tuesday at 2pm?",
                    "[READY_TO_PIN 2026-04-21T14:00:00Z]",
                ]
            )
        return MockLLMClient(canned_responses=["[READY_TO_PIN 2026-04-21T14:00:00Z]"])

    runner = ScenarioRunner(
        scenario=scenario,
        gt=gt,
        llm_factory=factory,
        db_path=tmp_path / "run.db",
        condition=AuditCondition.BASELINE,
    )
    result = await runner.run()
    assert result.terminal_predicate_passed is True

    eval_runner = EvalRunner()
    scorecard: RunScorecard = eval_runner.evaluate(
        action_log=runner.log,
        shadow_log=runner.shadow,
        gt=gt,
    )

    # Basic sanity checks
    assert scorecard.scenario_id == "cu-scheduling-mvp"
    assert set(scorecard.saf.dims.keys()) == {
        "recoverability",
        "policy_checkability",
        "attribution",
        "evidence_integrity",
        "phase_scoped_policy",
    }
    # Under baseline with MVP fixture (integrity_requirements: {outbound_message: 3},
    # all records stamped HASH_CHAINED=3 by the bus), evidence_integrity should be 0.75
    # (spec §3.2 weight for HASH_CHAINED meeting a HASH_CHAINED requirement).
    # Other dims all 1.0: no spurious records, no policies, no attribution DAG.
    assert scorecard.saf.dims["recoverability"] == 1.0
    assert scorecard.saf.dims["policy_checkability"] == 1.0
    assert scorecard.saf.dims["attribution"] == 1.0
    assert scorecard.saf.dims["evidence_integrity"] == 0.75
    assert scorecard.saf.dims["phase_scoped_policy"] == 1.0
    # Geometric mean with equal 1/5 weights = 0.75 ** (1/5) = 0.9440875...
    assert abs(scorecard.saf.overall - 0.75 ** (1 / 5)) < 1e-9
    # Evidence integrity should fail its 0.80 pass threshold
    assert scorecard.saf.passes["evidence_integrity"] is False
    assert scorecard.saf.passes["recoverability"] is True

    # Scorecard serializes cleanly to JSON
    payload = scorecard.model_dump_json()
    reloaded = json.loads(payload)
    assert reloaded["scenario_id"] == "cu-scheduling-mvp"


async def test_eval_runner_invalidates_tampered_log(tmp_path: Path):
    """When the primary log is tampered, Recoverability drops below 1.0."""
    loader = ScenarioLoader(root=FIXTURES)
    scenario, gt = loader.load("cu_scheduling_mvp")

    def factory(aid: str):
        if aid == "alice":
            return MockLLMClient(canned_responses=["[READY_TO_PIN 2026-04-21T14:00:00Z]"])
        return MockLLMClient(canned_responses=["[READY_TO_PIN 2026-04-21T14:00:00Z]"])

    runner = ScenarioRunner(
        scenario=scenario,
        gt=gt,
        llm_factory=factory,
        db_path=tmp_path / "run.db",
        condition=AuditCondition.BASELINE,
    )
    await runner.run()

    # Tamper: delete all alice rows from the primary log
    with runner.log.connect() as conn:
        conn.execute("DELETE FROM actions WHERE agent_id = 'alice'")
        conn.commit()

    eval_runner = EvalRunner()
    scorecard = eval_runner.evaluate(
        action_log=runner.log, shadow_log=runner.shadow, gt=gt
    )
    assert scorecard.saf.dims["recoverability"] < 1.0


async def test_eval_loads_gt_flat_policies_into_registry(tmp_path: Path):
    loader = ScenarioLoader(root=FIXTURES)
    scenario, gt = loader.load("cu_scheduling_mvp")
    # Inject a flat policy into GT for this test
    gt_with_policy = gt.model_copy(
        update={
            "policies": {
                "flat": [
                    {
                        "policy_id": "no-ssn",
                        "kind": "does_not_contain",
                        "params": {"substring": "ssn"},
                        "required_fields": ["payload.content"],
                    }
                ],
                "phase_scoped": [],
            }
        }
    )

    def factory(aid: str):
        return MockLLMClient(canned_responses=["[READY_TO_PIN 2026-04-21T14:00:00Z]"])

    runner = ScenarioRunner(
        scenario=scenario,
        gt=gt_with_policy,
        llm_factory=factory,
        db_path=tmp_path / "run.db",
        condition=AuditCondition.BASELINE,
    )
    await runner.run()

    eval_runner = EvalRunner()
    scorecard = eval_runner.evaluate(
        action_log=runner.log, shadow_log=runner.shadow, gt=gt_with_policy
    )
    # Policy Checkability should be 1.0 (required field is present)
    assert scorecard.saf.dims["policy_checkability"] == 1.0


async def test_eval_with_enforce_produces_nonempty_dag(tmp_path: Path):
    from clawsocialarena.audit.policies.dlp import RuleBasedDLP

    loader = ScenarioLoader(root=FIXTURES)
    scenario, gt = loader.load("cu_scheduling_mvp")

    def factory(aid: str):
        return MockLLMClient(
            canned_responses=["this contains secret data [READY_TO_PIN 2026-04-21T14:00:00Z]"]
        )

    runner = ScenarioRunner(
        scenario=scenario,
        gt=gt,
        llm_factory=factory,
        db_path=tmp_path / "run.db",
        condition=AuditCondition.ENFORCE,
    )
    # Inject DLP into the already-constructed AuditedMessageBus
    runner.bus._hooks = [RuleBasedDLP(forbidden_phrases=["secret"])]
    await runner.run()

    card = EvalRunner().evaluate(
        action_log=runner.log, shadow_log=runner.shadow, gt=gt
    )
    # Diagnostics should report chain integrity holds
    assert all(card.diagnostics["chain_integrity_primary"].values())
    # The attribution DAG should now have at least one L0 node from the DLP rewrite
    # (we verify via attribution score: an empty GT DAG + non-empty produced = 0.0)
    # Since our MVP GT has empty attribution_dag, a non-empty produced = attribution score 0.0
    assert card.saf.dims["attribution"] == 0.0
