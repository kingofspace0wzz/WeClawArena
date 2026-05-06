"""Tests for Phase E scheduling templates (MC, AM).

Each template must implement the :class:`Template` protocol, build
deterministically, and ship a valid shape per spec §4.3.
"""

from __future__ import annotations

from clawsocialarena.generator.registry import get_template, list_registered
from clawsocialarena.generator.template import CategoryCode, TaskFamily, Template
from clawsocialarena.generator.templates.am_scheduling import AMSchedulingTemplate
from clawsocialarena.generator.templates.cu_scheduling import CUSchedulingTemplate
from clawsocialarena.generator.templates.mc_scheduling import MCSchedulingTemplate


def test_mc_scheduling_implements_protocol():
    assert isinstance(MCSchedulingTemplate(), Template)


def test_am_scheduling_implements_protocol():
    assert isinstance(AMSchedulingTemplate(), Template)


def test_cu_scheduling_implements_protocol():
    assert isinstance(CUSchedulingTemplate(), Template)


def test_mc_scheduling_is_registered():
    pair = (CategoryCode.MC, TaskFamily.SCHEDULING)
    assert pair in list_registered()
    assert isinstance(get_template(*pair), MCSchedulingTemplate)


def test_am_scheduling_is_registered():
    pair = (CategoryCode.AM, TaskFamily.SCHEDULING)
    assert pair in list_registered()
    assert isinstance(get_template(*pair), AMSchedulingTemplate)


def test_cu_scheduling_is_registered():
    pair = (CategoryCode.CU, TaskFamily.SCHEDULING)
    assert pair in list_registered()
    assert isinstance(get_template(*pair), CUSchedulingTemplate)


def test_mc_scheduling_build_is_deterministic():
    t = MCSchedulingTemplate()
    a = t.build(seed=12, scenario_id="mc-sched-12")
    b = t.build(seed=12, scenario_id="mc-sched-12")
    assert a == b


def test_am_scheduling_build_is_deterministic():
    t = AMSchedulingTemplate()
    a = t.build(seed=3, scenario_id="am-sched-3")
    b = t.build(seed=3, scenario_id="am-sched-3")
    assert a == b


def test_cu_scheduling_declares_auditable_privacy_policy():
    shape = CUSchedulingTemplate().build(seed=4, scenario_id="cu-sched-4")
    flat_ids = {policy["policy_id"] for policy in shape.declared_policies["flat"]}
    assert "no-bob-private-notes-leak" in flat_ids


def test_mc_scheduling_shape_has_single_agent():
    shape = MCSchedulingTemplate().build(seed=5, scenario_id="mc-sched-5")
    assert shape.category == CategoryCode.MC
    assert shape.task_family == TaskFamily.SCHEDULING
    # MC = 1 mediator; NPC humans appear only in the action stream.
    assert len(shape.agents) == 1
    assert shape.terminal_predicate["type"] == "scheduling_pinned_slot"
    # Tool manifest and persona manifest are populated.
    assert "calendar" in shape.mcp_tool_manifest
    assert "mediator" in shape.persona_manifest
    # Two NPC outbound actions set up availability.
    npc_actions = [
        a for a in shape.injected_actions if a["action_type"] == "outbound_message"
    ]
    assert len(npc_actions) >= 2
    assert {a["agent_id"] for a in npc_actions} == {"npc-alex", "npc-blair"}


def test_mc_scheduling_mediator_allowlist_is_calendar_only():
    shape = MCSchedulingTemplate().build(seed=1, scenario_id="mc-sched-1")
    (mediator,) = shape.agents
    assert mediator["allowed_tools"] == ["calendar"]


def test_am_scheduling_shape_has_three_agents_with_tiers():
    shape = AMSchedulingTemplate().build(seed=7, scenario_id="am-sched-7")
    assert shape.category == CategoryCode.AM
    assert shape.task_family == TaskFamily.SCHEDULING
    assert len(shape.agents) == 3
    agent_ids = [a["agent_id"] for a in shape.agents]
    assert agent_ids == ["agent-close", "agent-peer", "agent-acquaintance"]
    # Asymmetric trust_estimate seeds appear in initial_state.
    trust = shape.initial_state["trust_estimate"]
    assert len(trust) == 3
    # Phase schedule covers all four planned phases.
    phases = [entry["phase"] for entry in shape.phase_schedule]
    assert "repair" in phases


def test_am_scheduling_has_per_agent_calendar_allowlist():
    shape = AMSchedulingTemplate().build(seed=1, scenario_id="am-sched-1")
    for agent in shape.agents:
        assert agent["allowed_tools"] == ["calendar"]
