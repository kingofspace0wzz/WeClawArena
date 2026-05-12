"""Phase 2 emitter tests: agent-graph-aware code paths.

Covers the consumer changes from the topology refactor
(docs/superpowers/specs/2026-05-09-clawsocialarena-v2-topology-design.md):
- compose_emitter renders one container per agent_graph node
- persona_emitter renders one persona pair per agent_graph node
- world_pack_instantiation.select_resources_for_family_pack returns
  declared resource_ids without category-based heuristics

Backward-compat coverage stays in the existing test files; this module
only exercises the new paths.
"""
from __future__ import annotations

import pytest

from clawsocialarena.generator.compose_emitter import emit_compose_yaml
from clawsocialarena.generator.persona_emitter import emit_persona_files
from clawsocialarena.generator.world_pack_instantiation import (
    select_resources_for_family_pack,
)
from clawsocialarena.scenario.models import (
    AgentGraph,
    AgentGraphEdge,
    AgentGraphNode,
    CoordinationMode,
    Scenario,
    ScenarioAgent,
)


def _node(agent_id: str, owner_id: str | None = None) -> AgentGraphNode:
    return AgentGraphNode(
        agent_id=agent_id,
        owner_id=owner_id or f"owner_{agent_id}",
        persona_source=f"personas/{agent_id}.md",
        role_label=f"role_{agent_id}",
        active_identity=f"{agent_id}@household",
        scope=["read:default"],
    )


def _edge(source: str, target: str) -> AgentGraphEdge:
    return AgentGraphEdge(
        source=source, target=target, relationship="peer_of", channel="dm"
    )


def _scenario_with_graph(
    *,
    agents: list[ScenarioAgent],
    graph: AgentGraph,
) -> Scenario:
    return Scenario(
        scenario_id="tau2_retail_household_001",
        category="ag-to-ag",
        task_family="coordination",
        agents=agents,
        initial_state={},
        max_turns=10,
        opening_message={"from": "system", "content": "go"},
        coordination_mode=CoordinationMode.GRAPH,
        agent_graph=graph,
        family_id="tau2_retail",
    )


def test_compose_emitter_uses_agent_graph_when_set() -> None:
    """Container layout follows agent_graph.nodes, not scenario.agents."""
    scenario = _scenario_with_graph(
        agents=[
            ScenarioAgent(
                agent_id="alice_assistant",
                user_id="alice",
                system_prompt_template="alice prompt",
            ),
            ScenarioAgent(
                agent_id="bob_assistant",
                user_id="bob",
                system_prompt_template="bob prompt",
            ),
        ],
        graph=AgentGraph(
            nodes=[_node("alice_assistant"), _node("bob_assistant")],
            edges=[_edge("alice_assistant", "bob_assistant")],
        ),
    )

    yaml = emit_compose_yaml(scenario)
    assert "alice_assistant" in yaml
    assert "bob_assistant" in yaml


def test_compose_emitter_falls_back_to_legacy_agents_when_no_graph() -> None:
    """Bundles without agent_graph keep the legacy ScenarioAgent path."""
    scenario = Scenario(
        scenario_id="legacy-001",
        category="cu",
        task_family="scheduling",
        agents=[
            ScenarioAgent(
                agent_id="legacy_a",
                user_id="user_a",
                system_prompt_template="a",
            ),
            ScenarioAgent(
                agent_id="legacy_b",
                user_id="user_b",
                system_prompt_template="b",
            ),
        ],
        initial_state={},
        max_turns=10,
        opening_message={"from": "system", "content": "go"},
    )

    yaml = emit_compose_yaml(scenario)
    assert "legacy_a" in yaml
    assert "legacy_b" in yaml


def test_persona_emitter_renders_role_and_identity_from_graph() -> None:
    """The persona Markdown for an agent_graph node carries Role and
    Active identity headers drawn from the graph node."""
    scenario = _scenario_with_graph(
        agents=[
            ScenarioAgent(
                agent_id="alice_assistant",
                user_id="alice",
                system_prompt_template="You assist alice.",
            ),
        ],
        graph=AgentGraph(
            nodes=[
                AgentGraphNode(
                    agent_id="alice_assistant",
                    owner_id="alice",
                    persona_source="personas/alice.md",
                    role_label="primary_account_holder",
                    active_identity="alice@household",
                    scope=["read:household_orders"],
                ),
            ],
            edges=[],
        ),
    )

    files = emit_persona_files(scenario)
    md = files["alice_assistant.system.md"]
    assert "alice_assistant" in md
    assert "**Role:** primary_account_holder" in md
    assert "**Active identity:** alice@household" in md
    assert "You assist alice." in md


def test_persona_emitter_handles_node_without_matching_scenario_agent() -> None:
    """When agent_graph declares an agent_id that has no matching
    ScenarioAgent (in-flight refactor), the emitter still renders the
    structural headers with an empty prompt body rather than crashing."""
    scenario = _scenario_with_graph(
        agents=[],
        graph=AgentGraph(
            nodes=[_node("orphan_agent")],
            edges=[],
        ),
    )

    files = emit_persona_files(scenario)
    md = files["orphan_agent.system.md"]
    assert "orphan_agent" in md
    assert "**Role:** role_orphan_agent" in md


def _build_minimal_pack(file_specs: list[tuple[str, str]], db_specs: list[str]):
    """Construct a minimal valid UserWorldPack for test purposes.

    Each file_spec is (resource_id, sensitivity_label). Each db_specs
    entry is just a resource_id. All resources are owned by 'alice'.
    """
    from clawsocialarena.worlds.models import (
        DatabaseResourceSpec,
        FileResourceSpec,
        OwnerPolicySpec,
        PersonaSpec,
        ProfileSourceSpec,
        ResourceCollectionSpec,
        ResourceRole,
        TableSpec,
        UserSpec,
        UserWorldPack,
        WorldPolicySpec,
    )

    user = UserSpec(
        user_id="alice",
        profile_source=ProfileSourceSpec(
            dataset="AgentSocialBench",
            dataset_version="1.0",
            profile_ref="asb://profiles/alice",
            profile_hash="sha256:abc123",
        ),
        persona=PersonaSpec(
            display_name="Alice",
            role="household_primary",
            goals=["place orders", "manage household"],
        ),
    )

    files = [
        FileResourceSpec(
            resource_id=rid,
            owner_id="alice",
            user_id="alice",
            path=f"files/{rid}.md",
            sensitivity=sens,
            roles=[ResourceRole.TASK_RELEVANT]
            if sens == "work"
            else [ResourceRole.PRIVACY_SENSITIVE],
            allowed_operations=["read"],
            expected_final_state="unchanged",
        )
        for rid, sens in file_specs
    ]
    databases = [
        DatabaseResourceSpec(
            resource_id=did,
            owner_id="alice",
            user_id="alice",
            path=f"db/{did}.sqlite",
            sensitivity="work",
            roles=[ResourceRole.TASK_RELEVANT],
            allowed_operations=["read"],
            expected_final_state="unchanged",
            tables={"t": TableSpec(columns={"id": "INTEGER"}, rows=[])},
        )
        for did in db_specs
    ]
    return UserWorldPack(
        world_id="test-world",
        schema_version="1",
        users=[user],
        resources=ResourceCollectionSpec(files=files, databases=databases),
        policies=WorldPolicySpec(
            owners={
                "alice": OwnerPolicySpec(
                    owner_id="alice", user_id="alice", display_name="Alice"
                )
            }
        ),
    )


def test_select_resources_for_family_pack_filters_to_declared_ids() -> None:
    """The family-pack-aware selector returns only the declared resource
    ids, dropping unknown ones silently. This is the targeted fix for
    the decoupled-resources defect from batch 0074."""
    pack = _build_minimal_pack(
        file_specs=[("pr-review-notes", "work"), ("custody-notes", "personal")],
        db_specs=["alice-orders-db"],
    )

    selected = select_resources_for_family_pack(
        pack=pack,
        family_id="tau2_retail",
        declared_resource_ids=["pr-review-notes", "alice-orders-db"],
        required_user_ids=["alice"],
    )

    # The family pack declared only the PR review file and the orders DB.
    # The custody notes file (irrelevant to PR review) must NOT be in
    # the selection, even though it lives in the same world pack.
    assert "pr-review-notes" in selected
    assert "alice-orders-db" in selected
    assert "custody-notes" not in selected


def test_select_resources_for_family_pack_drops_unknown_ids() -> None:
    """Unknown resource_ids are silently dropped (the caller validates
    if it wants a hard failure)."""
    pack = _build_minimal_pack(
        file_specs=[("real-file", "work")],
        db_specs=["real-db"],
    )

    selected = select_resources_for_family_pack(
        pack=pack,
        family_id="tau2_retail",
        declared_resource_ids=["real-file", "real-db", "ghost-resource"],
    )

    assert "real-file" in selected
    assert "real-db" in selected
    assert "ghost-resource" not in selected
