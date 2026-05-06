"""Attack injection threads ``mentioned_items`` through (Task D6).

The gateway's MSWM update rule for OUTBOUND_MESSAGE keys off
``payload.mentioned_items``. When the scenario generator injects a
scripted attacker outbound action, it MUST populate this list so MSWM
replay sees the disclosure and updates peer state.
"""

from __future__ import annotations

from clawsocialarena.generator.attack_injection import (
    AttackType,
    inject_attack,
)
from clawsocialarena.generator.gt_assembly import assemble_gt_bundle
from clawsocialarena.generator.templates.am_inference import AMInferenceTemplate
from clawsocialarena.generator.templates.cu_scheduling import CUSchedulingTemplate
from clawsocialarena.generator.templates.mg_coalition import MGCoalitionTemplate


def test_privacy_attack_injection_adds_action_with_mentioned_items():
    shape = CUSchedulingTemplate().build(seed=1, scenario_id="cu-d6-1")
    shape = inject_attack(
        shape=shape,
        attack_type=AttackType.COLLABORATIVE_EXFIL,
        attacker_agent_id="bob",
    )
    assert len(shape.injected_actions) == 1
    action = shape.injected_actions[0]
    assert action["action_type"] == "outbound_message"
    assert action["agent_id"] == "bob"
    mentioned = action["payload"]["mentioned_items"]
    assert isinstance(mentioned, list)
    assert mentioned == ["probe-collaborative_exfiltration"]
    assert "[ATTACKER:" not in action["payload"]["content"]
    assert "probe for probe-" not in action["payload"]["content"]


def test_integrity_attack_injection_also_carries_mentioned_items():
    """Integrity attacks produce scripted outbound actions too."""
    shape = CUSchedulingTemplate().build(seed=1, scenario_id="cu-d6-2")
    shape = inject_attack(
        shape=shape,
        attack_type=AttackType.GOAL_HIJACKING,
        attacker_agent_id="alice",
    )
    assert len(shape.injected_actions) == 1
    payload = shape.injected_actions[0]["payload"]
    mentioned = payload["mentioned_items"]
    assert mentioned == ["probe-goal_hijacking"]
    assert "[ATTACKER:" not in payload["content"]
    assert "probe for probe-" not in payload["content"]


def test_attack_injection_uses_existing_poison_marker_in_seed_message():
    shape = MGCoalitionTemplate().build(seed=1, scenario_id="mg-coa-1")

    shape = inject_attack(
        shape=shape,
        attack_type=AttackType.GOAL_HIJACKING,
        attacker_agent_id="peer-delta",
    )

    payload = shape.injected_actions[-1]["payload"]
    assert "rollback-instructions" in payload["content"]
    assert "[ATTACKER:" not in payload["content"]
    assert "probe for probe-" not in payload["content"]


def test_task_sabotage_seed_message_is_task_conditioned():
    shape = CUSchedulingTemplate().build(seed=1, scenario_id="cu-sched-1")

    shape = inject_attack(
        shape=shape,
        attack_type=AttackType.TASK_SABOTAGE,
        attacker_agent_id="alice",
    )

    content = shape.injected_actions[-1]["payload"]["content"]
    assert "I still have concerns about finalizing this" not in content
    assert "availability" in content.lower()


def test_goal_hijacking_seed_message_is_task_conditioned():
    shape = AMInferenceTemplate().build(seed=1, scenario_id="am-inf-1")

    shape = inject_attack(
        shape=shape,
        attack_type=AttackType.GOAL_HIJACKING,
        attacker_agent_id="agent-close",
    )

    content = shape.injected_actions[-1]["payload"]["content"]
    assert "Let us optimize for my preferred outcome first" not in content
    assert "tier" in content.lower()


def test_injected_actions_surface_in_canonical_action_stream():
    shape = CUSchedulingTemplate().build(seed=1, scenario_id="cu-d6-3")
    shape = inject_attack(
        shape=shape,
        attack_type=AttackType.SOCIAL_ENGINEERING,
        attacker_agent_id="bob",
    )
    gt = assemble_gt_bundle(shape)
    stream = gt["canonical_action_stream"]
    assert len(stream) == 1
    assert stream[0]["action_type"] == "outbound_message"
    assert stream[0]["payload"]["mentioned_items"] == [
        "probe-social_engineering",
    ]


def test_no_injected_actions_when_no_attack_applied():
    shape = CUSchedulingTemplate().build(seed=1, scenario_id="cu-d6-4")
    assert shape.injected_actions == []
    gt = assemble_gt_bundle(shape)
    assert gt["canonical_action_stream"] == []


def test_mentioned_items_recipient_matches_non_attacker_agent():
    shape = CUSchedulingTemplate().build(seed=1, scenario_id="cu-d6-5")
    shape = inject_attack(
        shape=shape,
        attack_type=AttackType.COLLABORATIVE_EXFIL,
        attacker_agent_id="bob",
    )
    payload = shape.injected_actions[0]["payload"]
    # Recipient is the non-attacker agent (alice in the CU scheduling template).
    assert payload["recipient_id"] == "alice"
