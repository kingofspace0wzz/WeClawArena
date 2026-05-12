"""Mode-shape validation tests for the topology layer.

Covers chain, tree, star, and graph mode validators against valid and
invalid AgentGraph shapes. See
docs/superpowers/specs/2026-05-09-clawsocialarena-v2-topology-design.md
section 4 for the rules being tested.
"""
from __future__ import annotations

import pytest

from clawsocialarena.generator.coordination_modes import (
    ShapeViolation,
    validate_mode_shape,
)
from clawsocialarena.scenario.models import (
    AgentGraph,
    AgentGraphEdge,
    AgentGraphNode,
    CoordinationMode,
)


def _node(agent_id: str) -> AgentGraphNode:
    return AgentGraphNode(
        agent_id=agent_id,
        owner_id=f"owner_{agent_id}",
        persona_source=f"personas/{agent_id}.md",
        role_label=f"role_{agent_id}",
        active_identity=f"{agent_id}@example",
        scope=[],
    )


def _edge(source: str, target: str, channel: str = "main") -> AgentGraphEdge:
    return AgentGraphEdge(
        source=source,
        target=target,
        relationship="peer_of",
        channel=channel,
    )


def test_chain_valid_three_node_path() -> None:
    graph = AgentGraph(
        nodes=[_node("a"), _node("b"), _node("c")],
        edges=[_edge("a", "b"), _edge("b", "c")],
    )
    violations = validate_mode_shape(CoordinationMode.CHAIN, graph)
    assert violations == []


def test_chain_rejects_branching() -> None:
    graph = AgentGraph(
        nodes=[_node("a"), _node("b"), _node("c"), _node("d")],
        edges=[_edge("a", "b"), _edge("b", "c"), _edge("b", "d")],
    )
    violations = validate_mode_shape(CoordinationMode.CHAIN, graph)
    assert violations
    assert any(v.kind.startswith("chain_") for v in violations)


def test_tree_valid_root_with_two_children() -> None:
    graph = AgentGraph(
        nodes=[_node("root"), _node("child1"), _node("child2")],
        edges=[_edge("root", "child1"), _edge("root", "child2")],
    )
    violations = validate_mode_shape(CoordinationMode.TREE, graph)
    assert violations == []


def test_tree_rejects_disconnected_components() -> None:
    graph = AgentGraph(
        nodes=[_node("a"), _node("b"), _node("c")],
        edges=[_edge("a", "b")],  # c is disconnected
    )
    violations = validate_mode_shape(CoordinationMode.TREE, graph)
    assert violations
    assert any("tree" in v.kind for v in violations)


def test_star_valid_hub_with_three_leaves() -> None:
    graph = AgentGraph(
        nodes=[_node("hub"), _node("a"), _node("b"), _node("c")],
        edges=[_edge("hub", "a"), _edge("hub", "b"), _edge("hub", "c")],
    )
    violations = validate_mode_shape(CoordinationMode.STAR, graph)
    assert violations == []


def test_star_rejects_leaf_to_leaf_edge() -> None:
    graph = AgentGraph(
        nodes=[_node("hub"), _node("a"), _node("b")],
        edges=[_edge("hub", "a"), _edge("hub", "b"), _edge("a", "b")],
    )
    violations = validate_mode_shape(CoordinationMode.STAR, graph)
    assert violations
    assert any("star" in v.kind for v in violations)


def test_graph_valid_peer_pairwise() -> None:
    graph = AgentGraph(
        nodes=[_node("a"), _node("b"), _node("c")],
        edges=[_edge("a", "b"), _edge("b", "c"), _edge("a", "c")],
    )
    violations = validate_mode_shape(CoordinationMode.GRAPH, graph)
    assert violations == []


def test_graph_warns_on_disconnected_components() -> None:
    graph = AgentGraph(
        nodes=[_node("a"), _node("b"), _node("c"), _node("d")],
        edges=[_edge("a", "b"), _edge("c", "d")],
    )
    violations = validate_mode_shape(CoordinationMode.GRAPH, graph)
    assert violations
    assert any("graph_disconnected" in v.kind for v in violations)


def test_too_small_for_each_mode() -> None:
    """All modes require at least 2 nodes."""
    single_node = AgentGraph(nodes=[_node("only")], edges=[])
    for mode in CoordinationMode:
        violations = validate_mode_shape(mode, single_node)
        assert violations, f"{mode} should reject a single-node graph"
