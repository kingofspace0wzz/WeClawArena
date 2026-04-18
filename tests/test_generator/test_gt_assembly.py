from clawsocialarena.generator.attack_injection import AttackType, inject_attack
from clawsocialarena.generator.gt_assembly import (
    assemble_gt_bundle,
    assemble_scenario_json,
)
from clawsocialarena.generator.templates.cu_scheduling import CUSchedulingTemplate
from clawsocialarena.scenario.models import GTBundle, Scenario


def test_assemble_gt_bundle_validates_schema():
    shape = CUSchedulingTemplate().build(seed=1, scenario_id="cu-1")
    gt = assemble_gt_bundle(shape)
    # Must validate as GTBundle
    GTBundle.model_validate(gt)


def test_assemble_scenario_json_validates_schema():
    shape = CUSchedulingTemplate().build(seed=1, scenario_id="cu-1")
    sc = assemble_scenario_json(shape)
    Scenario.model_validate(sc)


def test_privacy_attack_populates_attribution_dag():
    shape = CUSchedulingTemplate().build(seed=1, scenario_id="cu-1")
    shape = inject_attack(
        shape=shape,
        attack_type=AttackType.COLLABORATIVE_EXFIL,
        attacker_agent_id="bob",
    )
    gt = assemble_gt_bundle(shape)
    assert len(gt["attribution_dag"]["nodes"]) == 1
    assert gt["attribution_dag"]["nodes"][0]["agent_id"] == "bob"
