"""Core types for ClawSocialArena runtime and audit layer."""

from enum import IntEnum, StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ActionType(StrEnum):
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    OUTBOUND_MESSAGE = "outbound_message"
    MEMORY_WRITE = "memory_write"
    POLICY_DECISION = "policy_decision"
    DELEGATION_SPAWN = "delegation_spawn"
    RETRIEVAL_FETCH = "retrieval_fetch"
    TOOL_OBSERVATION_RETURN = "tool_observation_return"
    MEMORY_COMPRESSION = "memory_compression"
    SUMMARY_WRITE = "summary_write"


class IntegrityLevel(IntEnum):
    EXTERNAL = 1
    ADAPTER_SIGNED = 2
    HASH_CHAINED = 3
    CROSS_AGENT_SIGNED = 4


class AuditCondition(StrEnum):
    BASELINE = "baseline"
    PASSIVE = "passive"
    ENFORCE = "enforce"


class ExecutionPhase(StrEnum):
    NOMINAL = "nominal"
    RETRY = "retry"
    FALLBACK = "fallback"
    APPROVAL = "approval"
    DELEGATION = "delegation"


class SocialPhase(StrEnum):
    DISCOVERY = "discovery"
    NEGOTIATION = "negotiation"
    DISCLOSURE = "disclosure"
    BOUNDARY_SETTING = "boundary_setting"
    REPAIR = "repair"


class GovernanceRecord(BaseModel):
    """Per-action governance context bound into the action hash."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    owner_id: str = Field(min_length=1)
    active_identity_id: str = Field(min_length=1)
    authorization_scope_id: str = Field(min_length=1)
    approval_mandate_id: str = Field(min_length=1)
    escalation_state: str = Field(min_length=1)


class ActionRecord(BaseModel):
    """An immutable record of one action taken by an agent.

    See spec §2.4 for the schema and §2.3 for the ten action types.
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    action_id: str
    prev_hash: str
    agent_id: str
    action_type: ActionType
    timestamp: str
    execution_phase: ExecutionPhase
    social_phase: SocialPhase
    payload: dict[str, Any]
    integrity_level: IntegrityLevel
    signature: str | None = None
    source_action_ids: list[str] = Field(default_factory=list)
    """Explicit provenance links to upstream action_ids that causally precede
    this record. Empty by default; populated by the scenario/agent layer when
    the source chain is known. Consumers (e.g. AttributionGraphBuilder) walk
    these links to derive causal attribution without positional heuristics.
    """
    governance: GovernanceRecord | None = None

    @model_validator(mode="after")
    def _require_signature_above_hash_chained(self) -> "ActionRecord":
        if self.integrity_level >= IntegrityLevel.CROSS_AGENT_SIGNED and self.signature is None:
            raise ValueError(
                "signature is required for integrity_level >= CROSS_AGENT_SIGNED"
            )
        return self
