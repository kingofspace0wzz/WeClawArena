"""Tests for the cross_account retail loader."""
from __future__ import annotations

import pytest

from clawsocialarena.generator.family_packs.tau2_retail import load_cross_account_scenario
from clawsocialarena.scenario.models import CoordinationMode


def test_loader_produces_two_independent_customer_accounts() -> None:
    bundle = load_cross_account_scenario(task_index=0)
    graph = bundle.scenario.agent_graph
    assert graph is not None
    owners = {node.owner_id for node in graph.nodes}
    assert owners == {"carla", "diego"}
    assert bundle.family_pack_context["no_shared_account"] is True
    assert bundle.family_pack_context["archetype"] == "cross_account"


def test_loader_uses_graph_coordination_mode() -> None:
    bundle = load_cross_account_scenario(task_index=0)
    assert bundle.scenario.coordination_mode == CoordinationMode.GRAPH


def test_loader_rejects_out_of_range_task_index() -> None:
    with pytest.raises(ValueError, match="task_index out of range"):
        load_cross_account_scenario(task_index=99)


def test_loader_emits_six_distinct_base_tasks() -> None:
    bundles = [load_cross_account_scenario(task_index=i) for i in range(6)]
    scenario_ids = [b.scenario.scenario_id for b in bundles]
    assert len(set(scenario_ids)) == 6


def test_loader_consent_codes_propagate_to_family_pack_context() -> None:
    for i in range(6):
        bundle = load_cross_account_scenario(task_index=i)
        assert bundle.family_pack_context["recipient_consent_authorization_code"].startswith("DIEGO-CONSENT-")


def test_loader_max_turns_is_18() -> None:
    bundle = load_cross_account_scenario(task_index=0)
    assert bundle.scenario.max_turns == 18
