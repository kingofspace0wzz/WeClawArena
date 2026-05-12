"""Mode-shape validation helpers for the new topology layer.

Replaces the implicit topology assumptions baked into the per-category
Python templates (templates/cd_*.py, templates/hs_coalition.py, etc.)
with explicit shape constraints over a declared AgentGraph.

The four coordination modes are static topology declarations adopted
from MARBLE engine.engine.py (lines 200-573). We borrow the shape
labels and the relationship-triple data structure; the runtime
coordination loop in MARBLE is not adopted. The ClawSocialArena audit
gateway remains the runtime coordinator.

See docs/superpowers/specs/2026-05-09-clawsocialarena-v2-topology-design.md
for the full reference.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from clawsocialarena.scenario.models import (
    AgentGraph,
    CoordinationMode,
)


@dataclass(frozen=True)
class ShapeViolation:
    """One mode-shape violation detected on an AgentGraph.

    The kind field identifies the rule; the message is human-readable
    and suitable for scenario_validator error reporting.
    """

    kind: str
    message: str


def validate_mode_shape(
    coordination_mode: CoordinationMode,
    graph: AgentGraph,
) -> list[ShapeViolation]:
    """Return the list of shape violations the graph has under the mode.

    Empty list means the graph satisfies the mode's constraints. The
    caller (scenario_validator) is responsible for surfacing these as
    construction failures.
    """

    if coordination_mode is CoordinationMode.CHAIN:
        return _validate_chain(graph)
    if coordination_mode is CoordinationMode.TREE:
        return _validate_tree(graph)
    if coordination_mode is CoordinationMode.STAR:
        return _validate_star(graph)
    if coordination_mode is CoordinationMode.GRAPH:
        return _validate_graph(graph)
    return [
        ShapeViolation(
            kind="unknown_mode",
            message=f"unknown coordination_mode: {coordination_mode!r}",
        )
    ]


def _node_ids(graph: AgentGraph) -> set[str]:
    return {node.agent_id for node in graph.nodes}


def _adjacency(graph: AgentGraph) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        adj[edge.source].add(edge.target)
        adj[edge.target].add(edge.source)
    return adj


def _validate_chain(graph: AgentGraph) -> list[ShapeViolation]:
    """A chain is a single path: agent_1 -> agent_2 -> ... -> agent_n.

    Each interior node has exactly 2 neighbors, the two endpoints have
    exactly 1 neighbor, the graph is connected, and the edge count
    equals (node_count - 1).
    """
    nodes = _node_ids(graph)
    if len(nodes) < 2:
        return [
            ShapeViolation(
                kind="chain_too_short",
                message=f"chain requires at least 2 nodes, found {len(nodes)}",
            )
        ]
    adj = _adjacency(graph)
    if len(graph.edges) != len(nodes) - 1:
        return [
            ShapeViolation(
                kind="chain_edge_count",
                message=(
                    f"chain requires {len(nodes) - 1} edges, "
                    f"found {len(graph.edges)}"
                ),
            )
        ]
    endpoints = [aid for aid in nodes if len(adj[aid]) == 1]
    interior = [aid for aid in nodes if len(adj[aid]) == 2]
    others = [aid for aid in nodes if aid not in endpoints and aid not in interior]
    if len(endpoints) != 2 or others:
        return [
            ShapeViolation(
                kind="chain_degree",
                message=(
                    "chain requires exactly 2 endpoint nodes (degree 1) and "
                    "all others of degree 2; "
                    f"endpoints={endpoints}, interior_count={len(interior)}, "
                    f"others={others}"
                ),
            )
        ]
    if not _is_connected(nodes, adj):
        return [
            ShapeViolation(
                kind="chain_disconnected",
                message="chain edges do not form a connected graph",
            )
        ]
    return []


def _validate_tree(graph: AgentGraph) -> list[ShapeViolation]:
    """A tree has one root, no cycles, and one edge per non-root node."""
    nodes = _node_ids(graph)
    if len(nodes) < 2:
        return [
            ShapeViolation(
                kind="tree_too_small",
                message=f"tree requires at least 2 nodes, found {len(nodes)}",
            )
        ]
    if len(graph.edges) != len(nodes) - 1:
        return [
            ShapeViolation(
                kind="tree_edge_count",
                message=(
                    f"tree with {len(nodes)} nodes requires "
                    f"{len(nodes) - 1} edges, found {len(graph.edges)}"
                ),
            )
        ]
    adj = _adjacency(graph)
    if not _is_connected(nodes, adj):
        return [
            ShapeViolation(
                kind="tree_disconnected",
                message="tree edges do not form a connected graph",
            )
        ]
    # Tree connectedness + edge_count == node_count - 1 guarantees acyclicity.
    return []


def _validate_star(graph: AgentGraph) -> list[ShapeViolation]:
    """A star has exactly one hub; every other node connects only to the hub."""
    nodes = _node_ids(graph)
    if len(nodes) < 2:
        return [
            ShapeViolation(
                kind="star_too_small",
                message=f"star requires at least 2 nodes, found {len(nodes)}",
            )
        ]
    adj = _adjacency(graph)
    hub_candidates = [aid for aid in nodes if len(adj[aid]) == len(nodes) - 1]
    if len(hub_candidates) != 1:
        return [
            ShapeViolation(
                kind="star_no_unique_hub",
                message=(
                    "star requires exactly one hub connected to every other "
                    f"node; hub_candidates={hub_candidates}"
                ),
            )
        ]
    hub = hub_candidates[0]
    leaves = [aid for aid in nodes if aid != hub]
    bad_leaves = [aid for aid in leaves if adj[aid] != {hub}]
    if bad_leaves:
        return [
            ShapeViolation(
                kind="star_leaf_connectivity",
                message=(
                    "star leaves may only connect to the hub; "
                    f"bad_leaves={bad_leaves}"
                ),
            )
        ]
    return []


def _validate_graph(graph: AgentGraph) -> list[ShapeViolation]:
    """A graph mode allows any connected graph; warn on disconnected components."""
    nodes = _node_ids(graph)
    if len(nodes) < 2:
        return [
            ShapeViolation(
                kind="graph_too_small",
                message=f"graph requires at least 2 nodes, found {len(nodes)}",
            )
        ]
    adj = _adjacency(graph)
    if not _is_connected(nodes, adj):
        return [
            ShapeViolation(
                kind="graph_disconnected",
                message="graph mode contains disconnected components",
            )
        ]
    return []


def _is_connected(nodes: set[str], adj: dict[str, set[str]]) -> bool:
    if not nodes:
        return True
    start = next(iter(nodes))
    seen: set[str] = {start}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for neighbor in adj.get(current, set()):
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append(neighbor)
    return seen == nodes
