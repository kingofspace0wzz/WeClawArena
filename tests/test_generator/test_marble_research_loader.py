"""Tests for the marble_research family pack loader.

The loader now builds variable-N PI graphs (3, 4, or 5 PIs) from the
static MARBLE seed data. These tests exercise the default (3-PI task 0)
and selected multi-PI configurations to pin the contract.
"""
from __future__ import annotations

import pytest

from clawsocialarena.generator.family_packs.marble_research import (
    MarbleResearchLoader,
    load_research_collaboration_scenario,
)
from clawsocialarena.generator.family_packs.marble_research.marble_seed_data import (
    ALL_TASKS,
)
from clawsocialarena.scenario.models import CoordinationMode


def test_default_scenario_has_three_node_graph_and_family_id() -> None:
    """Default kwargs (task 0) should produce a 3-PI graph."""
    bundle = load_research_collaboration_scenario()
    assert bundle.scenario.family_id == "marble_research"
    assert bundle.scenario.coordination_mode == CoordinationMode.GRAPH
    assert len(bundle.scenario.agent_graph.nodes) == 3
    roles = {n.role_label for n in bundle.scenario.agent_graph.nodes}
    assert roles == {"convener_pi", "peer_pi"}


def test_convener_is_unique_and_alpha() -> None:
    """Default task 0 uses alpha as the convener."""
    bundle = load_research_collaboration_scenario()
    conveners = [
        n for n in bundle.scenario.agent_graph.nodes if n.role_label == "convener_pi"
    ]
    assert len(conveners) == 1
    assert conveners[0].owner_id == "alpha"


def test_graph_is_fully_connected_for_three_pis() -> None:
    bundle = load_research_collaboration_scenario()
    edges = bundle.scenario.agent_graph.edges
    # 3 nodes fully connected -> 3 * 2 = 6 directed edges
    assert len(edges) == 6
    sources = {e.source for e in edges}
    targets = {e.target for e in edges}
    assert sources == targets
    assert len(sources) == 3


@pytest.mark.parametrize("task_index, expected_n_pis", [
    (0, 3),   # PROP-7: alpha, beta, gamma
    (1, 4),   # PROP-12: alpha, beta, gamma, delta
    (2, 5),   # PROP-18: alpha, beta, gamma, delta, epsilon
    (3, 3),   # PROP-21: seed2, alpha, gamma, delta
    (4, 4),   # PROP-25: seed2, alpha, beta, gamma, delta
    (5, 3),   # PROP-30: seed3, alpha, beta, gamma
    (6, 4),   # PROP-35: seed3, alpha, beta, gamma, delta
    (7, 5),   # PROP-40: seed3, alpha, beta, gamma, delta, epsilon
])
def test_n_pi_graph_sizes(task_index: int, expected_n_pis: int) -> None:
    """Each task spec drives the correct graph size."""
    task = ALL_TASKS[task_index]
    bundle = load_research_collaboration_scenario(
        scenario_id=f"marble_research_collaboration_phase5_v{task_index}",
        seed_id=task.seed_id,
        proposal_id=task.proposal_id,
        convener_owner=task.convener_owner,
        convener_id=f"{task.convener_owner}_pi",
        participating_owners=task.participating_owners,
        proposal_topic_title=task.proposal_topic_title,
        proposal_topic_intro=task.proposal_topic_intro,
    )
    assert len(bundle.scenario.agent_graph.nodes) == expected_n_pis
    # Fully-connected directed: N*(N-1) edges
    assert len(bundle.scenario.agent_graph.edges) == expected_n_pis * (expected_n_pis - 1)


def test_evaluation_criteria_has_three_predicates() -> None:
    """Loader must emit all three env_assertion predicates."""
    bundle = load_research_collaboration_scenario()
    assertions = bundle.evaluation_criteria["env_assertions"]
    predicates = {a["predicate"] for a in assertions}
    assert predicates == {
        "proposal_has_complete_5q",
        "proposal_citations_authorized",
        "proposal_has_at_least_one_unpublished_citation",
    }
    for a in assertions:
        assert a["args"]["proposal_id"] == "PROP-7"


def test_evaluation_criteria_action_gate_is_finalize_proposal() -> None:
    bundle = load_research_collaboration_scenario()
    actions = bundle.evaluation_criteria["actions"]
    assert len(actions) == 1
    assert actions[0]["tool_name"] == "finalize_proposal"
    assert actions[0]["agent_id"] == "alpha_pi"


def test_pi_profiles_carry_research_summary() -> None:
    bundle = load_research_collaboration_scenario()
    assert len(bundle.pi_profiles) == 3
    for profile in bundle.pi_profiles:
        assert profile["lab"]
        assert profile["owner_id"]
        # New design uses research_summary from seed data (not profile_excerpt).
        assert profile["research_summary"]


def test_initial_state_carries_proposal_id_and_topic() -> None:
    bundle = load_research_collaboration_scenario()
    initial = bundle.scenario.initial_state
    assert initial["proposal_id"] == "PROP-7"
    assert "proposal_topic_title" in initial
    assert isinstance(initial.get("research_context_summary"), str)


def test_bundle_carries_seed_and_researchers() -> None:
    """The bundle must expose the seed and researcher list for the materializer."""
    bundle = load_research_collaboration_scenario()
    assert bundle.seed.seed_id == "interdisciplinary_tech"
    assert len(bundle.researchers) == 3
    owner_ids = [r.owner_id for r in bundle.researchers]
    assert owner_ids == ["alpha", "beta", "gamma"]


def test_phase_schedule_has_synthesis_and_approval() -> None:
    bundle = load_research_collaboration_scenario()
    phases = [phase["phase"] for phase in bundle.phase_schedule]
    assert "synthesis" in phases
    assert "approval" in phases


def test_declared_resource_ids_cover_all_pis() -> None:
    """Each participating PI must have a declared unpublished_results resource."""
    bundle = load_research_collaboration_scenario()
    rids = set(bundle.declared_resource_ids)
    for owner in ("alpha", "beta", "gamma"):
        assert f"pi.{owner}.unpublished_results" in rids
