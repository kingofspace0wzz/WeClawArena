import pytest

from clawsocialarena.generator.attack_injection import (
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
    prompt = [a for a in new_shape.agents if a["agent_id"] == "bob"][0][
        "system_prompt_template"
    ]
    assert "[ATTACKER]" not in prompt
    assert "Private objective:" in prompt


def test_inject_integrity_attack_adds_security_invariant():
    shape = CUSchedulingTemplate().build(seed=1, scenario_id="cu-1")
    new_shape = inject_attack(
        shape=shape,
        attack_type=AttackType.GOAL_HIJACKING,
        attacker_agent_id="alice",
    )
    assert len(new_shape.invariants["security_must_not_happen"]) == 1
    assert new_shape.invariants["security_must_not_happen"][0]["attack_type"] == "goal_hijacking"


def test_message_attack_plan_declares_recipe_stage_fields() -> None:
    shape = CUSchedulingTemplate().build(seed=1, scenario_id="cu-recipe")
    injected = inject_attack(
        shape=shape,
        attack_type=AttackType.GOAL_HIJACKING,
        attacker_agent_id=shape.agents[0]["agent_id"],
        declared_axis="collaboration",
    )

    assert injected.attack_plan["attack_recipe"] == "adaptive_malicious_peer"
    assert injected.attack_plan["attack_intensity"] == "standard"
    assert injected.attack_plan["delivery_surface"] == "message"
    assert injected.attack_plan["attacker_control"] == "scripted"
    assert injected.attack_plan["stage_expectations"]["attack_exposure"] is True
    assert injected.attack_plan["stage_expectations"]["target_compliance"] is True


def test_harmful_content_stress_attack_declares_cascade_minima() -> None:
    shape = CUSchedulingTemplate().build(seed=1, scenario_id="cu-cascade")
    injected = inject_attack(
        shape=shape,
        attack_type=AttackType.HARMFUL_CONTENT,
        attacker_agent_id=shape.agents[0]["agent_id"],
        attack_intensity="stress",
    )

    stage_expectations = injected.attack_plan["stage_expectations"]
    assert stage_expectations["cascade_depth_min"] == 1
    assert stage_expectations["cascade_breadth_min"] == 1


def test_inject_attack_emits_action_with_null_recipient_for_degenerate_shape() -> None:
    """A.2: when the participant pool has no non-attacker agent (some
    legacy MC mediator templates), construction proceeds and emits an
    action with recipient_id=None. The runner is expected to log this
    explicitly so the scorer can distinguish 'undelivered' from 'agent
    resisted'. The option 4 family-pack redesign eliminates the
    degenerate shape itself."""
    shape = CUSchedulingTemplate().build(seed=1, scenario_id="cu-degenerate")
    attacker_id = shape.agents[0]["agent_id"]
    degenerate_shape = shape.model_copy(update={
        "agents": [a for a in shape.agents if a["agent_id"] == attacker_id],
    })

    injected = inject_attack(
        shape=degenerate_shape,
        attack_type=AttackType.GOAL_HIJACKING,
        attacker_agent_id=attacker_id,
    )

    # Find the injected attack action.
    attack_actions = [
        a for a in injected.injected_actions
        if a.get("attack_type") == AttackType.GOAL_HIJACKING.value
    ]
    assert attack_actions, "expected at least one injected attack action"
    payload = attack_actions[0].get("payload") or {}
    # recipient_id is None for this legacy shape; runner-side guard
    # is responsible for surfacing the undelivered signal.
    assert payload.get("recipient_id") is None
