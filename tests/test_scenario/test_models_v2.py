"""Round-trip tests for v2 scenario models (§4.6).

The v2 GT bundle adds two new manifests:
- `mcp_tool_manifest: dict[str, McpToolSpec]` maps tool_name -> {schema, audit_class}.
- `persona_manifest:  dict[str, PersonaRef]`  maps agent_id -> {profile_ref, agent_id}.

These tests assert the model accepts canonical JSON, round-trips losslessly,
and keeps defaults backwards-compatible with the v1 bundle.
"""

from __future__ import annotations

import json

from clawsocialarena.scenario.models import GTBundle, McpToolSpec, PersonaRef


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


def test_mcp_tool_spec_fields():
    spec = McpToolSpec(
        schema={"type": "object"},
        audit_class="side_channel",
    )
    assert spec.audit_class == "side_channel"
    dumped = spec.model_dump()
    assert dumped == {"schema": {"type": "object"}, "audit_class": "side_channel"}


def test_persona_ref_fields():
    ref = PersonaRef(profile_ref="asb://profiles/carol-03", agent_id="carol")
    assert ref.agent_id == "carol"
    dumped = ref.model_dump()
    assert dumped == {"profile_ref": "asb://profiles/carol-03", "agent_id": "carol"}
