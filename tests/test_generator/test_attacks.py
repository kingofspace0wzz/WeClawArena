from clawsocialarena.generator.attacks import (
    AttackFamily,
    AttackType,
    ATTACK_FAMILY,
    inject_attack,
)
from clawsocialarena.generator.templates.cu_scheduling import CUSchedulingTemplate


def test_attack_family_mapping():
    assert ATTACK_FAMILY[AttackType.PROMPT_INJECTION] == AttackFamily.INTEGRITY
    assert ATTACK_FAMILY[AttackType.COLLABORATIVE_EXFIL] == AttackFamily.PRIVACY


def test_inject_privacy_attack_plants_disclosure():
    shape = CUSchedulingTemplate().build(seed=1, scenario_id="cu-1")
    new_shape = inject_attack(
        shape=shape,
        attack_type=AttackType.COLLABORATIVE_EXFIL,
        attacker_agent_id="bob",
    )
    assert len(new_shape.planted_disclosures) == 1
    assert new_shape.planted_disclosures[0]["agent_id"] == "bob"
    assert "[ATTACKER]" in [a for a in new_shape.agents if a["agent_id"] == "bob"][0]["system_prompt_template"]


def test_inject_integrity_attack_adds_security_invariant():
    shape = CUSchedulingTemplate().build(seed=1, scenario_id="cu-1")
    new_shape = inject_attack(
        shape=shape,
        attack_type=AttackType.GOAL_HIJACKING,
        attacker_agent_id="alice",
    )
    assert len(new_shape.invariants["security_must_not_happen"]) == 1
    assert new_shape.invariants["security_must_not_happen"][0]["attack_type"] == "goal_hijacking"
