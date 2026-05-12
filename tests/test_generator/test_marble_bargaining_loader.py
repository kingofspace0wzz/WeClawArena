"""Tests for the marble_bargaining family pack loader."""
from __future__ import annotations

from clawsocialarena.generator.family_packs.marble_bargaining import (
    MarbleBargainingLoader,
    load_bargaining_scenario,
)
from clawsocialarena.scenario.models import CoordinationMode


def test_scenario_has_two_node_graph_and_family_id() -> None:
    bundle = load_bargaining_scenario()
    assert bundle.scenario.family_id == "marble_bargaining"
    assert bundle.scenario.coordination_mode == CoordinationMode.GRAPH
    assert len(bundle.scenario.agent_graph.nodes) == 2
    roles = {n.role_label for n in bundle.scenario.agent_graph.nodes}
    assert roles == {"buyer", "seller"}


def test_default_constraints_create_valid_window() -> None:
    bundle = load_bargaining_scenario()
    assert bundle.seller_reservation < bundle.buyer_budget_ceiling, (
        "seller reservation must be below buyer budget for a deal to be possible"
    )
    assert bundle.market_reference_price >= bundle.seller_reservation
    assert bundle.market_reference_price <= bundle.buyer_budget_ceiling


def test_initial_state_carries_item_id_and_market_reference() -> None:
    bundle = load_bargaining_scenario()
    assert bundle.scenario.initial_state["item_id"] == "ITEM-7"
    assert bundle.scenario.initial_state["market_reference_price"] == bundle.market_reference_price


def test_evaluation_criteria_lists_window_predicate() -> None:
    bundle = load_bargaining_scenario()
    predicates = {
        a["predicate"] for a in bundle.evaluation_criteria["env_assertions"]
    }
    assert "agreement_recorded_for_item" in predicates
    assert "agreed_price_within_window" in predicates


def test_loader_kwargs_override_constraints() -> None:
    bundle = load_bargaining_scenario(
        buyer_budget_ceiling=100.0,
        seller_reservation=70.0,
        market_reference_price=85.0,
    )
    assert bundle.buyer_budget_ceiling == 100.0
    assert bundle.seller_reservation == 70.0
    assert bundle.market_reference_price == 85.0


def test_loader_reads_jsonl() -> None:
    loader = MarbleBargainingLoader()
    tasks = loader._load_tasks()
    assert tasks
    first = tasks[0]
    assert "agents" in first
