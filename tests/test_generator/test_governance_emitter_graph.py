"""Tests for the agent-graph-aware governance manifest emitter.

Covers the Phase 2B addition in
docs/superpowers/specs/2026-05-09-clawsocialarena-v2-topology-design.md
section 5: governance_emitter must read node.scope, node.approval_mandate,
edge.relationship, and emit a governance manifest.
"""
from __future__ import annotations

from clawsocialarena.generator.governance_emitter import (
    emit_governance_manifest_from_graph,
)
from clawsocialarena.scenario.models import (
    AgentGraph,
    AgentGraphEdge,
    AgentGraphNode,
)


def _node(
    agent_id: str,
    *,
    owner_id: str | None = None,
    scope: list[str] | None = None,
    approval_mandate: str = "self",
) -> AgentGraphNode:
    return AgentGraphNode(
        agent_id=agent_id,
        owner_id=owner_id or f"owner_{agent_id}",
        persona_source=f"personas/{agent_id}.md",
        role_label=f"role_{agent_id}",
        active_identity=f"{agent_id}@household",
        scope=scope or ["outbound_message"],
        approval_mandate=approval_mandate,
    )


def test_empty_graph_returns_normalized_empty_manifest() -> None:
    manifest = emit_governance_manifest_from_graph(None)
    assert manifest["owners"] == {}
    assert manifest["identities"] == {}
    assert manifest["authorization_scopes"] == {}
    assert manifest["approval_mandates"] == {}


def test_single_node_produces_one_owner_identity_scope_mandate() -> None:
    graph = AgentGraph(nodes=[_node("alice_assistant")], edges=[])
    manifest = emit_governance_manifest_from_graph(graph)

    assert "owner_alice_assistant" in manifest["owners"]
    assert "alice_assistant@household" in manifest["identities"]
    assert "scope-alice_assistant@household" in manifest["authorization_scopes"]
    assert "mandate-alice_assistant@household" in manifest["approval_mandates"]


def test_identity_carries_agent_id_and_owner_link() -> None:
    graph = AgentGraph(
        nodes=[_node("alice_assistant", owner_id="alice")],
        edges=[],
    )
    manifest = emit_governance_manifest_from_graph(graph)

    identity = manifest["identities"]["alice_assistant@household"]
    assert identity["owner_id"] == "alice"
    assert identity["agent_id"] == "alice_assistant"


def test_scope_records_allowed_actions_from_node_scope_field() -> None:
    graph = AgentGraph(
        nodes=[
            _node(
                "alice_assistant",
                scope=["read:household_orders", "write:household_orders"],
            )
        ],
        edges=[],
    )
    manifest = emit_governance_manifest_from_graph(graph)

    scope = manifest["authorization_scopes"]["scope-alice_assistant@household"]
    assert scope["allowed_actions"] == [
        "read:household_orders",
        "write:household_orders",
    ]


def test_mandate_carries_approval_mode_from_node() -> None:
    graph = AgentGraph(
        nodes=[
            _node(
                "bob_assistant",
                approval_mandate="primary_holder_required",
            )
        ],
        edges=[],
    )
    manifest = emit_governance_manifest_from_graph(graph)

    mandate = manifest["approval_mandates"]["mandate-bob_assistant@household"]
    assert mandate["approval_mode"] == "primary_holder_required"


def test_edges_become_relationships_table() -> None:
    graph = AgentGraph(
        nodes=[_node("alice"), _node("bob")],
        edges=[
            AgentGraphEdge(
                source="alice",
                target="bob",
                relationship="shares_account_with",
                channel="household_dm",
            ),
        ],
    )
    manifest = emit_governance_manifest_from_graph(graph)

    assert manifest["relationships"] == [
        {
            "source": "alice",
            "target": "bob",
            "relationship": "shares_account_with",
            "channel": "household_dm",
        }
    ]


def test_two_nodes_produce_two_owners_two_identities_two_scopes() -> None:
    graph = AgentGraph(
        nodes=[
            _node("alice_assistant", owner_id="alice"),
            _node("bob_assistant", owner_id="bob"),
        ],
        edges=[],
    )
    manifest = emit_governance_manifest_from_graph(graph)

    assert set(manifest["owners"].keys()) == {"alice", "bob"}
    assert len(manifest["identities"]) == 2
    assert len(manifest["authorization_scopes"]) == 2
    assert len(manifest["approval_mandates"]) == 2
