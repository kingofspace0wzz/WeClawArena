"""Tests for Phase E Cross-User Inference Containment templates.

Covers CD, MC, AM inference templates. Each template must:

- Implement the :class:`Template` protocol.
- Register under ``TaskFamily.INFERENCE``.
- Declare an ``inferential`` policy bucket with at least one
  ``must_not_decide`` predicate (spec §3.1 #1 / §4.3 Privacy axis).
- Ship a terminal_predicate of type ``inference_invariant_preserved``.
- Exclude tools that would trivialize the privacy task (empty
  ``allowed_tools`` per agent + empty ``mcp_tool_manifest``).
- Plant at least two NPC/agent outbound actions that introduce the
  protected items so joint-decidability has evidence to evaluate.
"""

from __future__ import annotations

from clawsocialarena.generator.registry import get_template, list_registered
from clawsocialarena.generator.template import CategoryCode, TaskFamily, Template
from clawsocialarena.generator.templates.am_inference import AMInferenceTemplate
from clawsocialarena.generator.templates.cd_inference import CDInferenceTemplate
from clawsocialarena.generator.templates.mc_inference import MCInferenceTemplate


_EXPECTED_AGENT_COUNTS = {
    CategoryCode.CD: 2,  # 2 agents + 1 NPC peer
    CategoryCode.MC: 1,  # 1 mediator + 2 NPCs
    CategoryCode.AM: 3,
}


def _all_inference_classes():
    return [CDInferenceTemplate, MCInferenceTemplate, AMInferenceTemplate]


def test_all_inference_templates_implement_protocol():
    for cls in _all_inference_classes():
        assert isinstance(cls(), Template)


def test_all_inference_templates_registered():
    reg = list_registered()
    for category in (CategoryCode.CD, CategoryCode.MC, CategoryCode.AM):
        assert (category, TaskFamily.INFERENCE) in reg
        assert isinstance(
            get_template(category, TaskFamily.INFERENCE), Template
        )


def test_inference_template_agent_counts_match_spec():
    for cls in _all_inference_classes():
        t = cls()
        shape = t.build(seed=1, scenario_id="inf")
        assert len(shape.agents) == _EXPECTED_AGENT_COUNTS[t.category]
        assert shape.task_family == TaskFamily.INFERENCE


def test_inference_terminal_predicate_is_inference_invariant():
    for cls in _all_inference_classes():
        shape = cls().build(seed=1, scenario_id="inf")
        pred = shape.terminal_predicate
        assert pred["type"] == "inference_invariant_preserved"
        assert pred["forbidden_inference_ids"]
        for entry in pred["forbidden_inference_ids"]:
            assert entry["for_agent"]
            assert entry["items"]


def test_inference_templates_declare_inferential_policy_bucket():
    for cls in _all_inference_classes():
        shape = cls().build(seed=1, scenario_id="inf")
        assert "inferential" in shape.declared_policies
        inf_policies = shape.declared_policies["inferential"]
        assert inf_policies, "inference templates must declare inferential policies"
        for p in inf_policies:
            assert p["type"] == "must_not_decide"
            assert p["for_agent"]
            assert p["forbidden_inference"]


def test_inference_policy_targets_are_modeled_conversation_actors():
    """Inferential policies must target actors represented in the trace.

    A synthetic observer with no message footprint cannot be checked by
    MSWM, so it makes SAF policy_checkability fail even when the run
    preserved every modeled privacy boundary.
    """
    for cls in _all_inference_classes():
        shape = cls().build(seed=1, scenario_id="inf")
        actors = {agent["agent_id"] for agent in shape.agents}
        actors.update({
            shape.opening_message["from"],
            shape.opening_message["to"],
        })
        for action in shape.injected_actions:
            actors.add(action["agent_id"])
            recipient = action.get("payload", {}).get("recipient_id")
            if recipient:
                actors.add(recipient)

        for policy in shape.declared_policies["inferential"]:
            assert policy["for_agent"] in actors
        for entry in shape.terminal_predicate["forbidden_inference_ids"]:
            assert entry["for_agent"] in actors


def test_inference_templates_withhold_tools_to_avoid_trivialization():
    """Privacy tasks must not hand agents a shared tool that would leak
    items by side channel. Every inference template ships an empty MCP
    tool manifest and empty per-agent allowlists."""
    for cls in _all_inference_classes():
        shape = cls().build(seed=1, scenario_id="inf")
        assert shape.mcp_tool_manifest == {}
        for agent in shape.agents:
            assert agent["allowed_tools"] == []


def test_inference_templates_plant_at_least_two_injected_actions():
    for cls in _all_inference_classes():
        shape = cls().build(seed=1, scenario_id="inf")
        outbound = [
            a for a in shape.injected_actions if a["action_type"] == "outbound_message"
        ]
        assert len(outbound) >= 2


def test_inference_templates_have_privacy_invariants():
    for cls in _all_inference_classes():
        shape = cls().build(seed=1, scenario_id="inf")
        inv = shape.invariants["privacy_must_not_cross"]
        assert len(inv) >= 1


def test_inference_templates_deterministic_build():
    for cls in _all_inference_classes():
        t = cls()
        a = t.build(seed=11, scenario_id="inf-11")
        b = t.build(seed=11, scenario_id="inf-11")
        assert a == b


def test_cd_inference_has_npc_witness_in_actions():
    shape = CDInferenceTemplate().build(seed=1, scenario_id="cd-inf-1")
    agent_ids_in_actions = {a["agent_id"] for a in shape.injected_actions}
    # NPC peer (npc-witness) must be one of the action senders.
    assert "npc-witness" in agent_ids_in_actions


def test_mc_inference_has_both_npcs_disclosing():
    shape = MCInferenceTemplate().build(seed=1, scenario_id="mc-inf-1")
    senders = {a["agent_id"] for a in shape.injected_actions}
    assert "npc-alex" in senders
    assert "npc-blair" in senders


def test_am_inference_has_three_tiered_agents():
    shape = AMInferenceTemplate().build(seed=1, scenario_id="am-inf-1")
    agent_ids = [a["agent_id"] for a in shape.agents]
    assert agent_ids == ["agent-close", "agent-peer", "agent-acquaintance"]
    # The trust map on initial_state carries three directed-pair entries.
    assert len(shape.initial_state["trust_estimate"]) == 3
