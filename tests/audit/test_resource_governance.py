"""Resource-aware governance policy tests."""

from __future__ import annotations

from clawsocialarena.audit.policies.governance import GovernancePolicyHook
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    GovernanceRecord,
    IntegrityLevel,
    SocialPhase,
)


def _governance_manifest() -> dict:
    return {
        "owners": {"owner-alice": {"owner_id": "owner-alice"}},
        "identities": {
            "identity-alice-primary": {
                "identity_id": "identity-alice-primary",
                "owner_id": "owner-alice",
                "agent_id": "alice",
            }
        },
        "authorization_scopes": {
            "scope-alice-files": {
                "scope_id": "scope-alice-files",
                "owner_id": "owner-alice",
                "identity_id": "identity-alice-primary",
                "resource_ids": ["file-alice-notes"],
                "allowed_actions": ["fs.read", "fs.delete"],
            }
        },
        "approval_mandates": {
            "mandate-none": {
                "mandate_id": "mandate-none",
                "owner_id": "owner-alice",
                "scope_id": "scope-alice-files",
                "approval_mode": "none",
            }
        },
        "escalation_rules": {},
    }


def _resource_manifest(*, operations: list[str], consent_required: bool) -> dict:
    return {
        "resources": {
            "file-alice-notes": {
                "resource_id": "file-alice-notes",
                "type": "file",
                "owner_id": "owner-alice",
                "sensitivity": "confidential",
                "path": "files/alice/private-notes.md",
                "consent_required": consent_required,
                "allowed_operations": [
                    {
                        "identity_id": "identity-alice-primary",
                        "scope_id": "scope-alice-files",
                        "operations": operations,
                    }
                ],
            }
        }
    }


def _action(arguments: dict) -> ActionRecord:
    return ActionRecord(
        action_id="tc-resource",
        prev_hash="0" * 64,
        agent_id="alice",
        action_type=ActionType.TOOL_CALL,
        timestamp="2026-04-30T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={"tool_name": "fs.delete", "arguments": arguments},
        integrity_level=IntegrityLevel.HASH_CHAINED,
        governance=GovernanceRecord(
            owner_id="owner-alice",
            active_identity_id="identity-alice-primary",
            authorization_scope_id="scope-alice-files",
            approval_mandate_id="mandate-none",
            escalation_state="not_required",
        ),
    )


def test_resource_operation_not_allowed_by_manifest_blocks() -> None:
    hook = GovernancePolicyHook(
        _governance_manifest(),
        resource_manifest=_resource_manifest(
            operations=["fs.read"],
            consent_required=False,
        ),
    )

    decision = hook.evaluate(
        action=_action(
            {
                "resource_id": "file-alice-notes",
                "identity_id": "identity-alice-primary",
                "scope_id": "scope-alice-files",
            }
        ),
        context={},
    )

    assert decision.verdict == "block"
    assert "resource_operation_not_allowed" in decision.governance_verdict[
        "violations"
    ]


def test_consent_required_resource_mutation_blocks_without_consent() -> None:
    hook = GovernancePolicyHook(
        _governance_manifest(),
        resource_manifest=_resource_manifest(
            operations=["fs.delete"],
            consent_required=True,
        ),
    )

    decision = hook.evaluate(
        action=_action(
            {
                "resource_id": "file-alice-notes",
                "identity_id": "identity-alice-primary",
                "scope_id": "scope-alice-files",
            }
        ),
        context={},
    )

    assert decision.verdict == "block"
    assert "resource_consent_missing" in decision.governance_verdict["violations"]


def test_consent_required_resource_mutation_allows_with_consent() -> None:
    hook = GovernancePolicyHook(
        _governance_manifest(),
        resource_manifest=_resource_manifest(
            operations=["fs.delete"],
            consent_required=True,
        ),
    )

    decision = hook.evaluate(
        action=_action(
            {
                "resource_id": "file-alice-notes",
                "identity_id": "identity-alice-primary",
                "scope_id": "scope-alice-files",
                "consent_granted": True,
            }
        ),
        context={},
    )

    assert decision.verdict == "allow"
