"""Round-trip tests for v2 scenario models (§4.6).

The v2 GT bundle adds two new manifests:
- `mcp_tool_manifest: dict[str, McpToolSpec]` maps tool_name -> {schema, audit_class}.
- `persona_manifest:  dict[str, PersonaRef]`  maps agent_id -> {profile_ref, agent_id}.

These tests assert the model accepts canonical JSON, round-trips losslessly,
and keeps defaults backwards-compatible with the v1 bundle.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from clawsocialarena.scenario.models import (
    ApprovalMandate,
    AuthorizationScope,
    EscalationRule,
    GTBundle,
    GovernanceManifest,
    McpToolSpec,
    PersonaRef,
    Scenario,
)


def _canonical_v2_gt_bundle() -> dict:
    return {
        "scenario_id": "cu-scheduling-v2",
        "canonical_action_stream": [],
        "phase_schedule": [
            {"phase": "discovery", "start_turn": 0, "end_turn": 2},
            {"phase": "negotiation", "start_turn": 2, "end_turn": 8},
        ],
        "policies": {"flat": [], "phase_scoped": []},
        "attribution_dag": {"nodes": [], "edges": []},
        "integrity_requirements": {"outbound_message": 3},
        "terminal_predicate": {
            "type": "scheduling_pinned_slot",
            "valid_window": {
                "start": "2026-04-20T09:00:00Z",
                "end": "2026-04-23T17:00:00Z",
            },
        },
        "invariants": {"privacy_must_not_cross": [], "security_must_not_happen": []},
        "attack_plan": None,
        "mcp_tool_manifest": {
            "calendar": {
                "schema": {
                    "type": "object",
                    "properties": {"slot": {"type": "string"}},
                    "required": ["slot"],
                },
                "audit_class": "outbound_message",
            },
            "ledger": {
                "schema": {"type": "object"},
                "audit_class": "side_channel",
            },
        },
        "persona_manifest": {
            "alice": {"profile_ref": "asb://profiles/alice-01", "agent_id": "alice"},
            "bob": {"profile_ref": "asb://profiles/bob-02", "agent_id": "bob"},
        },
    }


def _canonical_governance_manifest() -> dict:
    return {
        "owners": {
            "owner-alice": {
                "owner_id": "owner-alice",
                "user_id": "user-a",
                "display_name": "Alice",
            }
        },
        "identities": {
            "identity-alice-delegate": {
                "identity_id": "identity-alice-delegate",
                "owner_id": "owner-alice",
                "agent_id": "alice",
                "label": "Alice scheduling delegate",
            }
        },
        "authorization_scopes": {
            "scope-calendar-write": {
                "scope_id": "scope-calendar-write",
                "owner_id": "owner-alice",
                "identity_id": "identity-alice-delegate",
                "resource_ids": ["calendar://alice/work"],
                "allowed_actions": ["calendar.read", "calendar.write"],
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
            "rule-denied": {
                "rule_id": "rule-denied",
                "from_state": "pending_owner_review",
                "to_state": "blocked",
                "trigger": "owner_denied",
                "required_actor_id": "owner-alice",
            }
        },
    }


def test_gt_bundle_v2_round_trips_through_json():
    canonical = _canonical_v2_gt_bundle()
    gt = GTBundle.model_validate(canonical)
    # mcp_tool_manifest is parsed as McpToolSpec values
    assert isinstance(gt.mcp_tool_manifest["calendar"], McpToolSpec)
    assert gt.mcp_tool_manifest["calendar"].audit_class == "outbound_message"
    # persona_manifest is parsed as PersonaRef values
    assert isinstance(gt.persona_manifest["alice"], PersonaRef)
    assert gt.persona_manifest["alice"].profile_ref == "asb://profiles/alice-01"

    # Round trip through JSON
    serialized = json.loads(gt.model_dump_json())
    # mcp_tool_manifest stays a dict of dicts with schema + audit_class
    assert serialized["mcp_tool_manifest"]["calendar"]["audit_class"] == "outbound_message"
    assert serialized["mcp_tool_manifest"]["calendar"]["schema"]["type"] == "object"
    assert serialized["persona_manifest"]["bob"]["profile_ref"] == "asb://profiles/bob-02"

    # Reparsing the serialized JSON yields an equal bundle
    gt2 = GTBundle.model_validate(serialized)
    assert gt2 == gt


def test_gt_bundle_v2_defaults_backwards_compatible():
    """A v1-style GT bundle (no mcp_tool_manifest / persona_manifest) still loads."""
    v1 = {
        "scenario_id": "cu-v1",
        "canonical_action_stream": [],
        "phase_schedule": [],
        "policies": {"flat": [], "phase_scoped": []},
        "attribution_dag": {"nodes": [], "edges": []},
        "integrity_requirements": {},
        "terminal_predicate": {"type": "scheduling_pinned_slot"},
        "invariants": {},
        "attack_plan": None,
    }
    gt = GTBundle.model_validate(v1)
    assert gt.mcp_tool_manifest == {}
    assert gt.persona_manifest == {}
    assert gt.governance_manifest is None


def test_mcp_tool_spec_fields():
    spec = McpToolSpec(
        schema={"type": "object"},
        audit_class="side_channel",
    )
    assert spec.audit_class == "side_channel"
    dumped = spec.model_dump()
    assert dumped == {"schema": {"type": "object"}, "audit_class": "side_channel"}
    assert spec.input_schema == {"type": "object"}


def test_persona_ref_fields():
    ref = PersonaRef(profile_ref="asb://profiles/carol-03", agent_id="carol")
    assert ref.agent_id == "carol"
    dumped = ref.model_dump()
    assert dumped == {"profile_ref": "asb://profiles/carol-03", "agent_id": "carol"}


def test_scenario_agent_defaults_owner_and_identity_metadata_round_trip():
    scenario = Scenario.model_validate(
        {
            "scenario_id": "cu-governance-v1",
            "category": "CU",
            "task_family": "scheduling",
            "agents": [
                {
                    "agent_id": "alice",
                    "user_id": "user-a",
                    "system_prompt_template": "p",
                    "default_owner_id": "owner-alice",
                    "default_identity_id": "identity-alice-delegate",
                }
            ],
            "initial_state": {},
            "max_turns": 4,
            "opening_message": {"from": "alice", "to": "alice", "content": "start"},
        }
    )

    dumped = scenario.model_dump()

    assert dumped["agents"][0]["default_owner_id"] == "owner-alice"
    assert dumped["agents"][0]["default_identity_id"] == "identity-alice-delegate"
    assert Scenario.model_validate(dumped) == scenario


def test_governance_manifest_round_trips_in_gt_bundle():
    canonical = _canonical_v2_gt_bundle()
    canonical["governance_manifest"] = _canonical_governance_manifest()

    gt = GTBundle.model_validate(canonical)

    assert isinstance(gt.governance_manifest, GovernanceManifest)
    assert isinstance(
        gt.governance_manifest.authorization_scopes["scope-calendar-write"],
        AuthorizationScope,
    )
    assert isinstance(
        gt.governance_manifest.approval_mandates["mandate-owner-approval"],
        ApprovalMandate,
    )
    assert isinstance(
        gt.governance_manifest.escalation_rules["rule-denied"],
        EscalationRule,
    )
    dumped = json.loads(gt.model_dump_json())
    assert dumped["governance_manifest"] == canonical["governance_manifest"]
    assert GTBundle.model_validate(dumped) == gt


def test_governance_manifest_rejects_missing_owner_reference():
    manifest = _canonical_governance_manifest()
    manifest["identities"]["identity-alice-delegate"]["owner_id"] = "missing-owner"

    with pytest.raises(ValidationError):
        GovernanceManifest.model_validate(manifest)
