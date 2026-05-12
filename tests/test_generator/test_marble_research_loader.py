"""Tests for the marble_research family pack loader."""
from __future__ import annotations

from clawsocialarena.generator.family_packs.marble_research import (
    MarbleResearchLoader,
    load_research_collaboration_scenario,
)
from clawsocialarena.scenario.models import CoordinationMode


def test_scenario_has_three_node_graph_and_family_id() -> None:
    bundle = load_research_collaboration_scenario()
    assert bundle.scenario.family_id == "marble_research"
    assert bundle.scenario.coordination_mode == CoordinationMode.GRAPH
    assert len(bundle.scenario.agent_graph.nodes) == 3
    roles = {n.role_label for n in bundle.scenario.agent_graph.nodes}
    assert roles == {"convener_pi", "peer_pi"}


def test_convener_is_unique() -> None:
    bundle = load_research_collaboration_scenario()
    conveners = [
        n for n in bundle.scenario.agent_graph.nodes if n.role_label == "convener_pi"
    ]
    assert len(conveners) == 1
    assert conveners[0].owner_id == "alice"


def test_graph_is_fully_connected_among_three_pis() -> None:
    bundle = load_research_collaboration_scenario()
    edges = bundle.scenario.agent_graph.edges
    # 3 nodes fully connected -> 3 * 2 = 6 directed edges
    assert len(edges) == 6
    sources = {e.source for e in edges}
    targets = {e.target for e in edges}
    assert sources == targets
    assert len(sources) == 3


def test_evaluation_criteria_uses_proposal_id() -> None:
    bundle = load_research_collaboration_scenario()
    assertions = bundle.evaluation_criteria["env_assertions"]
    predicates = {a["predicate"] for a in assertions}
    assert "proposal_has_complete_5q" in predicates
    assert "proposal_citations_authorized" in predicates
    for a in assertions:
        assert a["args"]["proposal_id"] == "PROP-7"


def test_pi_profiles_pulled_from_marble_source() -> None:
    bundle = load_research_collaboration_scenario()
    assert len(bundle.pi_profiles) == 3
    # Each PI should carry at least some non-empty profile excerpt
    # sourced from MARBLE.
    for profile in bundle.pi_profiles:
        assert profile["lab"]
        assert profile["owner_id"]


def test_initial_state_carries_research_context_and_proposal_id() -> None:
    bundle = load_research_collaboration_scenario()
    assert bundle.scenario.initial_state["proposal_id"] == "PROP-7"
    assert isinstance(bundle.scenario.initial_state["research_context"], str)


def test_phase_schedule_has_synthesis_and_approval() -> None:
    bundle = load_research_collaboration_scenario()
    phases = [phase["phase"] for phase in bundle.phase_schedule]
    assert "synthesis" in phases
    assert "approval" in phases


def test_loader_reads_jsonl() -> None:
    loader = MarbleResearchLoader()
    tasks = loader._load_tasks()
    assert tasks, "marble research_main.jsonl should have at least one task"
    first = tasks[0]
    assert "agents" in first
    assert len(first["agents"]) >= 3
