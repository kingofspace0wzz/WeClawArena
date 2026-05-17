"""Tests for the store_rep_dyad retail loader."""
from __future__ import annotations

import pytest

from clawsocialarena.generator.family_packs.tau2_retail import load_store_rep_dyad_scenario
from clawsocialarena.scenario.models import CoordinationMode


def test_loader_produces_customer_and_store_rep() -> None:
    bundle = load_store_rep_dyad_scenario(task_index=0)
    graph = bundle.scenario.agent_graph
    assert graph is not None
    owners = {node.owner_id for node in graph.nodes}
    assert owners == {"evelyn", "retail_rep_07"}
    assert bundle.family_pack_context["archetype"] == "store_rep_dyad"


def test_loader_includes_authentication_action() -> None:
    bundle = load_store_rep_dyad_scenario(task_index=0)
    tool_names = {a["tool_name"] for a in bundle.evaluation_criteria["actions"]}
    assert ("find_user_id_by_name_zip" in tool_names) or ("find_user_id_by_email" in tool_names)


def test_loader_carries_store_policy_override_code() -> None:
    bundle = load_store_rep_dyad_scenario(task_index=0)
    assert bundle.family_pack_context["store_policy_override_authorization_code"].startswith("STORE-OVERRIDE-")


def test_loader_rejects_out_of_range() -> None:
    with pytest.raises(ValueError, match="task_index out of range"):
        load_store_rep_dyad_scenario(task_index=99)


def test_loader_emits_six_distinct_base_tasks() -> None:
    bundles = [load_store_rep_dyad_scenario(task_index=i) for i in range(6)]
    scenario_ids = [b.scenario.scenario_id for b in bundles]
    assert len(set(scenario_ids)) == 6


def test_loader_max_turns_is_12() -> None:
    bundle = load_store_rep_dyad_scenario(task_index=0)
    assert bundle.scenario.max_turns == 12


def test_loader_uses_graph_coordination_mode() -> None:
    bundle = load_store_rep_dyad_scenario(task_index=0)
    assert bundle.scenario.coordination_mode == CoordinationMode.GRAPH
