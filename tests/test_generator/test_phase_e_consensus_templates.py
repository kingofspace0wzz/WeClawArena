"""Tests for Phase E consensus-allocation templates (CD, MG, HS, CM).

Each template registers under ``TaskFamily.CONSENSUS`` and produces a
shape whose terminal_predicate is ``consensus_ledger_agreement`` with
the agent count prescribed by spec §4.1 / §4.2.
"""

from __future__ import annotations

from clawsocialarena.generator.registry import get_template, list_registered
from clawsocialarena.generator.template import CategoryCode, TaskFamily, Template
from clawsocialarena.generator.templates.cd_consensus import CDConsensusTemplate
from clawsocialarena.generator.templates.cm_consensus import CMConsensusTemplate
from clawsocialarena.generator.templates.hs_consensus import HSConsensusTemplate
from clawsocialarena.generator.templates.mg_consensus import MGConsensusTemplate


_EXPECTED_AGENT_COUNTS = {
    CategoryCode.CD: 2,
    CategoryCode.MG: 4,
    CategoryCode.HS: 4,  # 1 hub + 3 spokes
    CategoryCode.CM: 3,
}


def _all_consensus_classes():
    return [
        CDConsensusTemplate,
        MGConsensusTemplate,
        HSConsensusTemplate,
        CMConsensusTemplate,
    ]


def test_all_consensus_templates_implement_protocol():
    for cls in _all_consensus_classes():
        assert isinstance(cls(), Template)


def test_all_consensus_templates_registered():
    reg = list_registered()
    for category in (CategoryCode.CD, CategoryCode.MG, CategoryCode.HS, CategoryCode.CM):
        assert (category, TaskFamily.CONSENSUS) in reg
        t = get_template(category, TaskFamily.CONSENSUS)
        assert isinstance(t, Template)


def test_consensus_template_agent_counts_match_spec():
    for cls in _all_consensus_classes():
        t = cls()
        shape = t.build(seed=1, scenario_id=f"{t.category.value.lower()}-consensus-1")
        assert len(shape.agents) == _EXPECTED_AGENT_COUNTS[t.category]
        assert shape.task_family == TaskFamily.CONSENSUS
        assert shape.terminal_predicate["type"] == "consensus_ledger_agreement"


def test_consensus_template_ledger_tool_present():
    for cls in _all_consensus_classes():
        shape = cls().build(seed=2, scenario_id="cons-2")
        assert "ledger" in shape.mcp_tool_manifest
        assert shape.mcp_tool_manifest["ledger"]["audit_class"] == "tool_call"
        for agent in shape.agents:
            assert agent["allowed_tools"] == ["ledger"]


def test_consensus_template_determinism():
    for cls in _all_consensus_classes():
        t = cls()
        a = t.build(seed=9, scenario_id="dup")
        b = t.build(seed=9, scenario_id="dup")
        assert a == b


def test_hs_consensus_uses_weighted_fairness():
    shape = HSConsensusTemplate().build(seed=1, scenario_id="hs-1")
    pred = shape.terminal_predicate
    assert pred["fairness"] == "weighted_by_stakes"
    stakes = pred["stakes"]
    # Spokes carry positive stakes; the hub carries zero so the
    # proportional split never allocates to the hub.
    assert stakes["hub"] == 0.0
    assert stakes["spoke-1"] > 0


def test_consensus_template_phase_schedule_non_empty():
    for cls in _all_consensus_classes():
        shape = cls().build(seed=1, scenario_id="cons")
        assert len(shape.phase_schedule) >= 2
        phases = [entry["phase"] for entry in shape.phase_schedule]
        assert "discovery" in phases
        assert "negotiation" in phases


def test_consensus_template_privacy_invariants_present():
    for cls in _all_consensus_classes():
        shape = cls().build(seed=1, scenario_id="cons")
        inv = shape.invariants["privacy_must_not_cross"]
        assert len(inv) >= 1
        # Each invariant lists an owner + at least one item.
        for entry in inv:
            assert entry["owner"]
            assert entry["items"]


def test_mg_consensus_has_4_participants_in_terminal_predicate():
    shape = MGConsensusTemplate().build(seed=1, scenario_id="mg-1")
    pred = shape.terminal_predicate
    assert len(pred["participants"]) == 4


def test_cd_consensus_agents_have_distinct_users():
    shape = CDConsensusTemplate().build(seed=1, scenario_id="cd-1")
    user_ids = [a["user_id"] for a in shape.agents]
    assert len(set(user_ids)) == len(user_ids)
