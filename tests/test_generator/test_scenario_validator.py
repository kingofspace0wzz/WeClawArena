"""Scenario validator tests for the topology refactor.

Covers the structural validation rules declared in
docs/superpowers/specs/2026-05-09-clawsocialarena-v2-topology-design.md
section 4, plus the backward-compatibility rule that scenarios without
agent_graph still pass.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.generator.scenario_validator import (
    ValidationError,
    validate_scenario,
)
from clawsocialarena.scenario.models import (
    AgentGraph,
    AgentGraphEdge,
    AgentGraphNode,
    CoordinationMode,
    Scenario,
    ScenarioAgent,
)


def _legacy_scenario() -> Scenario:
    """Scenario with no topology fields. Represents legacy template path."""
    return Scenario(
        scenario_id="legacy-001",
        category="cu",
        task_family="scheduling",
        agents=[
            ScenarioAgent(
                agent_id="alice",
                user_id="user_alice",
                system_prompt_template="prompt",
            ),
            ScenarioAgent(
                agent_id="bob",
                user_id="user_bob",
                system_prompt_template="prompt",
            ),
        ],
        initial_state={},
        max_turns=10,
        opening_message={"from": "system", "content": "go"},
    )


def _node(agent_id: str, owner_id: str | None = None) -> AgentGraphNode:
    return AgentGraphNode(
        agent_id=agent_id,
        owner_id=owner_id or f"owner_{agent_id}",
        persona_source=f"personas/{agent_id}.md",
        role_label=f"role_{agent_id}",
        active_identity=f"{agent_id}@example",
        scope=["read:default"],
    )


def _edge(source: str, target: str, channel: str = "main") -> AgentGraphEdge:
    return AgentGraphEdge(
        source=source,
        target=target,
        relationship="peer_of",
        channel=channel,
    )


def test_legacy_scenario_without_topology_fields_passes() -> None:
    """Backward compatibility: bundles produced before the topology
    refactor lack coordination_mode and agent_graph and must still
    validate."""
    scenario = _legacy_scenario()
    result = validate_scenario(scenario)
    assert result.passed
    assert result.errors == ()


def test_topology_fields_must_be_paired() -> None:
    """A scenario with coordination_mode but no agent_graph (or vice
    versa) is an error."""
    scenario = _legacy_scenario().model_copy(
        update={"coordination_mode": CoordinationMode.GRAPH}
    )
    result = validate_scenario(scenario)
    assert not result.passed
    rules = {error.rule for error in result.errors}
    assert "topology_fields_paired" in rules


def test_duplicate_agent_id_rejected() -> None:
    scenario = _legacy_scenario().model_copy(update={
        "coordination_mode": CoordinationMode.GRAPH,
        "agent_graph": AgentGraph(
            nodes=[_node("alice"), _node("alice", owner_id="owner_bob")],
            edges=[_edge("alice", "alice")],
        ),
    })
    result = validate_scenario(scenario, allow_shared_ownership=True)
    rules = {error.rule for error in result.errors}
    assert "agent_id_unique" in rules


def test_duplicate_owner_id_rejected() -> None:
    """The Camila persona-aliasing defect from batch 0074: two graph
    nodes with the same owner_id."""
    scenario = _legacy_scenario().model_copy(update={
        "coordination_mode": CoordinationMode.GRAPH,
        "agent_graph": AgentGraph(
            nodes=[
                _node("a1", owner_id="camila"),
                _node("a2", owner_id="camila"),
            ],
            edges=[_edge("a1", "a2")],
        ),
    })
    result = validate_scenario(scenario)
    rules = {error.rule for error in result.errors}
    assert "owner_id_unique" in rules


def test_shared_ownership_allowed_when_flag_set() -> None:
    """Some legitimate scenarios (one principal running two automation
    assistants) need allow_shared_ownership=True to pass."""
    scenario = _legacy_scenario().model_copy(update={
        "coordination_mode": CoordinationMode.GRAPH,
        "agent_graph": AgentGraph(
            nodes=[
                _node("a1", owner_id="alice"),
                _node("a2", owner_id="alice"),
            ],
            edges=[_edge("a1", "a2")],
        ),
    })
    result = validate_scenario(scenario, allow_shared_ownership=True)
    rules = {error.rule for error in result.errors}
    assert "owner_id_unique" not in rules


def test_dangling_edge_endpoint_rejected() -> None:
    scenario = _legacy_scenario().model_copy(update={
        "coordination_mode": CoordinationMode.GRAPH,
        "agent_graph": AgentGraph(
            nodes=[_node("a"), _node("b")],
            edges=[_edge("a", "nonexistent")],
        ),
    })
    result = validate_scenario(scenario)
    rules = {error.rule for error in result.errors}
    assert "edge_endpoints" in rules


def test_unknown_channel_rejected_when_manifest_provided() -> None:
    scenario = _legacy_scenario().model_copy(update={
        "coordination_mode": CoordinationMode.GRAPH,
        "agent_graph": AgentGraph(
            nodes=[_node("a"), _node("b")],
            edges=[_edge("a", "b", channel="not_registered")],
        ),
    })
    result = validate_scenario(
        scenario, channel_manifest={"household_dm", "household_group"}
    )
    rules = {error.rule for error in result.errors}
    assert "edge_channel_registered" in rules


def test_unknown_scope_rejected_when_vocabulary_provided() -> None:
    scenario = _legacy_scenario().model_copy(update={
        "coordination_mode": CoordinationMode.GRAPH,
        "agent_graph": AgentGraph(
            nodes=[
                AgentGraphNode(
                    agent_id="a",
                    owner_id="alice",
                    persona_source="personas/a.md",
                    role_label="role_a",
                    active_identity="a@example",
                    scope=["read:default", "bogus:scope"],
                ),
                _node("b"),
            ],
            edges=[_edge("a", "b")],
        ),
    })
    result = validate_scenario(
        scenario, scope_vocabulary={"read:default"}
    )
    rules = {error.rule for error in result.errors}
    assert "scope_vocabulary" in rules


def test_full_valid_scenario_passes() -> None:
    """End-to-end pass: graph mode, distinct owners, valid edges, valid
    scopes, registered channels."""
    scenario = _legacy_scenario().model_copy(update={
        "coordination_mode": CoordinationMode.GRAPH,
        "agent_graph": AgentGraph(
            nodes=[_node("a"), _node("b"), _node("c")],
            edges=[
                _edge("a", "b", channel="dm"),
                _edge("b", "c", channel="dm"),
                _edge("a", "c", channel="dm"),
            ],
        ),
        "family_id": "marble_research",
    })
    result = validate_scenario(
        scenario,
        channel_manifest={"dm"},
        scope_vocabulary={"read:default"},
    )
    assert result.passed, result.errors


def test_chain_mode_with_branching_fails() -> None:
    """A four-node Y (center b connects to a, c, and d) is not a path."""
    scenario = _legacy_scenario().model_copy(update={
        "coordination_mode": CoordinationMode.CHAIN,
        "agent_graph": AgentGraph(
            nodes=[_node("a"), _node("b"), _node("c"), _node("d")],
            edges=[_edge("a", "b"), _edge("b", "c"), _edge("b", "d")],
        ),
    })
    result = validate_scenario(scenario)
    assert not result.passed
    rules = {error.rule for error in result.errors}
    assert any(rule.startswith("mode_shape:chain_") for rule in rules)
