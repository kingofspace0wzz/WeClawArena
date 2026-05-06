"""Tests for the runtime governance policy hook."""

from __future__ import annotations

import pytest

from clawsocialarena.audit.policies.governance import GovernancePolicyHook
from clawsocialarena.scenario.models import GovernanceManifest
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    GovernanceRecord,
    IntegrityLevel,
    SocialPhase,
)


def _manifest() -> GovernanceManifest:
    return GovernanceManifest.model_validate(
        {
            "owners": {
                "owner-alice": {
                    "owner_id": "owner-alice",
                    "user_id": "user-a",
                    "display_name": "Alice",
                },
                "owner-bob": {
                    "owner_id": "owner-bob",
                    "user_id": "user-b",
                    "display_name": "Bob",
                },
            },
            "identities": {
                "identity-alice-delegate": {
                    "identity_id": "identity-alice-delegate",
                    "owner_id": "owner-alice",
                    "agent_id": "alice",
                    "label": "Alice delegate",
                },
                "identity-bob-delegate": {
                    "identity_id": "identity-bob-delegate",
                    "owner_id": "owner-bob",
                    "agent_id": "bob",
                    "label": "Bob delegate",
                },
            },
            "authorization_scopes": {
                "scope-calendar-write": {
                    "scope_id": "scope-calendar-write",
                    "owner_id": "owner-alice",
                    "identity_id": "identity-alice-delegate",
                    "resource_ids": ["calendar://alice/work"],
                    "allowed_actions": ["calendar.write"],
                    "constraints": {},
                }
            },
            "approval_mandates": {
                "mandate-owner-approval": {
                    "mandate_id": "mandate-owner-approval",
                    "owner_id": "owner-alice",
                    "scope_id": "scope-calendar-write",
                    "approver_ids": ["owner-alice"],
                    "approval_mode": "owner_explicit",
                }
            },
            "escalation_rules": {
                "rule-approved": {
                    "rule_id": "rule-approved",
                    "from_state": "pending_owner_review",
                    "to_state": "approved",
                    "trigger": "owner_approved",
                    "required_actor_id": "owner-alice",
                },
                "rule-denied": {
                    "rule_id": "rule-denied",
                    "from_state": "pending_owner_review",
                    "to_state": "blocked",
                    "trigger": "owner_denied",
                    "required_actor_id": "owner-alice",
                },
            },
        }
    )


def _governance(**overrides: str) -> GovernanceRecord:
    data = {
        "owner_id": "owner-alice",
        "active_identity_id": "identity-alice-delegate",
        "authorization_scope_id": "scope-calendar-write",
        "approval_mandate_id": "mandate-owner-approval",
        "escalation_state": "approved",
    }
    data.update(overrides)
    return GovernanceRecord(**data)


def _action(
    governance: GovernanceRecord | None = None,
    *,
    payload: dict | None = None,
    action_type: ActionType = ActionType.TOOL_CALL,
    agent_id: str = "alice",
) -> ActionRecord:
    return ActionRecord(
        action_id="act-1",
        prev_hash="0" * 64,
        agent_id=agent_id,
        action_type=action_type,
        timestamp="2026-04-27T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload=payload
        or {
            "tool_name": "calendar",
            "arguments": {
                "action": "calendar.write",
                "resource_id": "calendar://alice/work",
            },
        },
        integrity_level=IntegrityLevel.HASH_CHAINED,
        governance=governance,
    )


def test_permitted_governed_action_allows_with_structured_verdict() -> None:
    hook = GovernancePolicyHook(_manifest())

    decision = hook.evaluate(action=_action(_governance()), context={})

    assert decision.verdict == "allow"
    assert decision.policy_id == "governance"
    assert decision.governance_verdict == {
        "decision": "allow",
        "violations": [],
        "requires_owner_approval": False,
        "manifest_refs": {
            "owner_id": "owner-alice",
            "active_identity_id": "identity-alice-delegate",
            "authorization_scope_id": "scope-calendar-write",
            "approval_mandate_id": "mandate-owner-approval",
            "escalation_rule_ids": ["rule-approved", "rule-denied"],
        },
    }


def test_action_without_governance_is_logged_as_not_governed() -> None:
    hook = GovernancePolicyHook(_manifest())

    decision = hook.evaluate(action=_action(None), context={})

    assert decision.verdict == "allow"
    assert decision.governance_verdict["decision"] == "not_governed"
    assert decision.governance_verdict["violations"] == []


@pytest.mark.parametrize(
    ("governance", "payload", "expected_violation"),
    [
        (
            _governance(owner_id="owner-bob"),
            {
                "tool_name": "calendar",
                "arguments": {
                    "action": "calendar.write",
                    "resource_id": "calendar://alice/work",
                },
            },
            "owner_identity_mismatch",
        ),
        (
            _governance(active_identity_id="identity-bob-delegate"),
            {
                "tool_name": "calendar",
                "arguments": {
                    "action": "calendar.write",
                    "resource_id": "calendar://alice/work",
                },
            },
            "identity_agent_mismatch",
        ),
        (
            _governance(),
            {
                "tool_name": "calendar",
                "arguments": {
                    "action": "calendar.write",
                    "resource_id": "calendar://alice/private",
                },
            },
            "resource_out_of_scope",
        ),
        (
            _governance(escalation_state="pending_owner_review"),
            {
                "tool_name": "calendar",
                "arguments": {
                    "action": "calendar.write",
                    "resource_id": "calendar://alice/work",
                },
            },
            "owner_approval_missing",
        ),
        (
            _governance(escalation_state="denied"),
            {
                "tool_name": "calendar",
                "arguments": {
                    "action": "calendar.write",
                    "resource_id": "calendar://alice/work",
                },
            },
            "escalation_denied",
        ),
    ],
)
def test_governance_violations_block(
    governance: GovernanceRecord,
    payload: dict,
    expected_violation: str,
) -> None:
    hook = GovernancePolicyHook(_manifest())

    decision = hook.evaluate(
        action=_action(governance, payload=payload),
        context={},
    )

    assert decision.verdict == "block"
    assert expected_violation in decision.governance_verdict["violations"]
    assert decision.governance_verdict["decision"] == "block"
