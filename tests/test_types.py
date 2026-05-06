import pytest
from pydantic import ValidationError
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    GovernanceRecord,
    IntegrityLevel,
    AuditCondition,
    ExecutionPhase,
    SocialPhase,
)


def test_action_type_has_all_ten_types():
    expected = {
        "llm_call",
        "tool_call",
        "outbound_message",
        "memory_write",
        "policy_decision",
        "delegation_spawn",
        "retrieval_fetch",
        "tool_observation_return",
        "memory_compression",
        "summary_write",
    }
    assert {t.value for t in ActionType} == expected


def test_integrity_level_ordinal():
    assert IntegrityLevel.EXTERNAL < IntegrityLevel.ADAPTER_SIGNED
    assert IntegrityLevel.ADAPTER_SIGNED < IntegrityLevel.HASH_CHAINED
    assert IntegrityLevel.HASH_CHAINED < IntegrityLevel.CROSS_AGENT_SIGNED


def test_audit_condition_values():
    assert AuditCondition("baseline")
    assert AuditCondition("passive")
    assert AuditCondition("enforce")


def test_action_record_minimal():
    rec = ActionRecord(
        action_id="abc",
        prev_hash="0" * 64,
        agent_id="agent-a",
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-15T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={"to": "agent-b", "content": "hello"},
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )
    assert rec.agent_id == "agent-a"
    assert rec.integrity_level == IntegrityLevel.HASH_CHAINED


def test_action_record_requires_signature_at_high_integrity():
    with pytest.raises(ValidationError):
        ActionRecord(
            action_id="abc",
            prev_hash="0" * 64,
            agent_id="agent-a",
            action_type=ActionType.OUTBOUND_MESSAGE,
            timestamp="2026-04-15T00:00:00Z",
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=SocialPhase.DISCOVERY,
            payload={"to": "agent-b", "content": "hello"},
            integrity_level=IntegrityLevel.CROSS_AGENT_SIGNED,
            signature=None,
        )


def test_action_record_governance_round_trips_through_json():
    rec = ActionRecord(
        action_id="abc",
        prev_hash="0" * 64,
        agent_id="agent-a",
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-15T00:00:00Z",
        execution_phase=ExecutionPhase.APPROVAL,
        social_phase=SocialPhase.NEGOTIATION,
        payload={"to": "agent-b", "content": "please approve"},
        integrity_level=IntegrityLevel.HASH_CHAINED,
        governance=GovernanceRecord(
            owner_id="owner-alice",
            active_identity_id="identity-alice-delegate",
            authorization_scope_id="scope-calendar-write",
            approval_mandate_id="mandate-owner-approval",
            escalation_state="pending_owner_review",
        ),
    )

    rebuilt = ActionRecord.model_validate_json(rec.model_dump_json())

    assert rebuilt == rec
    assert rebuilt.governance is not None
    assert rebuilt.governance.owner_id == "owner-alice"
    assert rebuilt.governance.escalation_state == "pending_owner_review"


def test_action_record_governance_requires_all_fields():
    with pytest.raises(ValidationError):
        GovernanceRecord(
            owner_id="owner-alice",
            active_identity_id="identity-alice-delegate",
            authorization_scope_id="scope-calendar-write",
            escalation_state="pending_owner_review",
        )
