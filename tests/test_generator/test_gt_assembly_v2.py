"""GT assembly v2 tests (Task D5).

GT assembly now emits the v2 fields required by spec §4.6:

- ``mcp_tool_manifest`` :: ``{tool: {schema, audit_class}}`` pulled from the
  template.
- ``persona_manifest`` :: ``{agent_id: {profile_ref, agent_id}}``. When the
  template does not populate an explicit persona manifest, assembly falls
  back to synthesising one from the scenario's agents so every bundle ships
  with a complete manifest.
"""

from __future__ import annotations

from clawsocialarena.generator.gt_assembly import assemble_gt_bundle
from clawsocialarena.generator.template import TemplateShape, CategoryCode, TaskFamily
from clawsocialarena.generator.templates.cu_scheduling import CUSchedulingTemplate
from clawsocialarena.scenario.models import GTBundle


def _shape_with_manifests() -> TemplateShape:
    return TemplateShape(
        scenario_id="cu-v2-1",
        category=CategoryCode.CU,
        task_family=TaskFamily.SCHEDULING,
        agents=[
            {"agent_id": "alice", "user_id": "user-a", "system_prompt_template": "p"},
            {"agent_id": "bob", "user_id": "user-b", "system_prompt_template": "q"},
        ],
        initial_state={},
        max_turns=8,
        opening_message={"from": "alice", "to": "bob", "content": "hi"},
        phase_schedule=[],
        declared_policies={"flat": [], "phase_scoped": []},
        terminal_predicate={"type": "scheduling_pinned_slot"},
        invariants={},
        integrity_requirements={},
        planted_disclosures=[],
        mcp_tool_manifest={
            "calendar": {
                "schema": {"type": "object"},
                "audit_class": "outbound_message",
            },
        },
        persona_manifest={
            "alice": {"profile_ref": "asb://alice-01", "agent_id": "alice"},
            "bob": {"profile_ref": "asb://bob-02", "agent_id": "bob"},
        },
    )


def test_gt_bundle_v2_contains_mcp_and_persona_manifests():
    gt_dict = assemble_gt_bundle(_shape_with_manifests())
    assert "mcp_tool_manifest" in gt_dict
    assert "persona_manifest" in gt_dict
    assert gt_dict["mcp_tool_manifest"]["calendar"]["audit_class"] == "outbound_message"
    assert gt_dict["persona_manifest"]["alice"]["profile_ref"] == "asb://alice-01"


def test_gt_bundle_v2_validates_as_pydantic_model():
    gt_dict = assemble_gt_bundle(_shape_with_manifests())
    parsed = GTBundle.model_validate(gt_dict)
    assert parsed.mcp_tool_manifest["calendar"].audit_class == "outbound_message"
    assert parsed.persona_manifest["alice"].profile_ref == "asb://alice-01"
    assert parsed.persona_manifest["bob"].agent_id == "bob"


def test_gt_bundle_v2_synthesizes_persona_manifest_when_template_omits_it():
    """Legacy templates (CU scheduling) do not declare persona_manifest.

    Assembly falls back to a sensible default: one entry per scenario agent,
    keyed by agent_id, with ``profile_ref = asb://profiles/<agent_id>``.
    """
    shape = CUSchedulingTemplate().build(seed=1, scenario_id="cu-legacy")
    gt_dict = assemble_gt_bundle(shape)
    pm = gt_dict["persona_manifest"]
    assert set(pm.keys()) == {"alice", "bob"}
    for agent_id, ref in pm.items():
        assert ref["agent_id"] == agent_id
        assert ref["profile_ref"].endswith(agent_id)


def test_gt_bundle_v2_mcp_manifest_defaults_empty_when_template_omits_it():
    shape = CUSchedulingTemplate().build(seed=1, scenario_id="cu-legacy")
    gt_dict = assemble_gt_bundle(shape)
    assert gt_dict["mcp_tool_manifest"] == {}


def test_gt_bundle_v2_round_trips_with_canonical_action_stream():
    shape = _shape_with_manifests()
    gt_dict = assemble_gt_bundle(shape)
    assert isinstance(gt_dict["canonical_action_stream"], list)
    parsed = GTBundle.model_validate(gt_dict)
    # Round-trip through model_dump to make sure manifests survive.
    dumped = parsed.model_dump()
    assert dumped["mcp_tool_manifest"]["calendar"]["audit_class"] == "outbound_message"
    assert dumped["persona_manifest"]["bob"]["profile_ref"] == "asb://bob-02"
