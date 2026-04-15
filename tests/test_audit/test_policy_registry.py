from pathlib import Path

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.policy_registry import (
    FlatPolicy,
    PhaseScopedPolicy,
    PolicyRegistry,
)
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


def _rec(content: str, phase: SocialPhase = SocialPhase.DISCOVERY) -> ActionRecord:
    return ActionRecord(
        action_id="a-1",
        prev_hash="0" * 64,
        agent_id="alice",
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-15T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=phase,
        payload={"content": content},
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def test_flat_policy_evaluates_on_action():
    reg = PolicyRegistry()
    reg.register_flat(
        FlatPolicy(
            policy_id="no-ssn",
            predicate=lambda action, ctx: "ssn" not in action.payload.get("content", "").lower(),
            required_fields={"payload.content"},
        )
    )
    clean = _rec("hello")
    bad = _rec("My SSN is 123-45-6789")
    assert reg.evaluate_flat(clean, ctx={}) == {"no-ssn": True}
    assert reg.evaluate_flat(bad, ctx={}) == {"no-ssn": False}


def test_phase_scoped_policy_applies_only_in_phase():
    reg = PolicyRegistry()
    reg.register_phase_scoped(
        PhaseScopedPolicy(
            policy_id="no-disclosure-in-discovery",
            phase=SocialPhase.DISCOVERY,
            predicate=lambda action, ctx: "health"
            not in action.payload.get("content", "").lower(),
            required_fields={"payload.content"},
        )
    )
    action = _rec("I have health issues")
    assert reg.evaluate_phase_scoped(
        action, ctx={}, current_phase=SocialPhase.DISCOVERY
    ) == {"no-disclosure-in-discovery": False}
    assert reg.evaluate_phase_scoped(
        action, ctx={}, current_phase=SocialPhase.NEGOTIATION
    ) == {"no-disclosure-in-discovery": None}


def test_registry_exposes_policy_collections():
    reg = PolicyRegistry()
    reg.register_flat(
        FlatPolicy(
            policy_id="p1",
            predicate=lambda action, ctx: True,
            required_fields={"payload.content"},
        )
    )
    reg.register_phase_scoped(
        PhaseScopedPolicy(
            policy_id="p2",
            phase=SocialPhase.DISCOVERY,
            predicate=lambda action, ctx: True,
            required_fields=set(),
        )
    )
    assert len(reg.flat_policies) == 1
    assert len(reg.scoped_policies) == 1
    assert reg.flat_policies[0].policy_id == "p1"
    assert reg.scoped_policies[0].policy_id == "p2"
