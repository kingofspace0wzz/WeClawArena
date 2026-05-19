"""Tests for the owned-ecosystem marble_bidding family pack loader."""
from __future__ import annotations

import pytest

from clawsocialarena.generator.phase5_task_variants import task_variants_for
from clawsocialarena.generator.family_packs.marble_bidding import (
    load_bidding_scenario,
)
from clawsocialarena.scenario.models import CoordinationMode


def test_bidding_task_variants_are_seed_sourced() -> None:
    variants = task_variants_for("marble_bidding")

    assert len(variants) == 12
    assert [variant.task_index for variant in variants] == list(range(12))
    assert len({v.loader_kwargs["auction_id"] for v in variants}) == 12
    assert len({v.loader_kwargs["resource_profile"] for v in variants}) == 12
    assert {len(v.loader_kwargs["buyer_owners"]) for v in variants} == {2, 3, 4}


def test_bidding_cell_task_slices_do_not_overlap() -> None:
    cm = task_variants_for("marble_bidding", cell_id="CM-C-marble_bidding")
    cu = task_variants_for("marble_bidding", cell_id="CU-C-marble_bidding")

    assert len(cm) == 6
    assert len(cu) == 6
    assert [variant.task_index for variant in cm] == list(range(6))
    assert [variant.task_index for variant in cu] == list(range(6))
    assert {
        variant.loader_kwargs["auction_id"] for variant in cm
    }.isdisjoint({variant.loader_kwargs["auction_id"] for variant in cu})
    assert all(
        variant.loader_kwargs["resource_profile"].startswith(
            "owned_ecosystem_cu_bidding_"
        )
        for variant in cu
    )
    assert {variant.loader_kwargs["category"] for variant in cm} == {"CM"}
    assert {variant.loader_kwargs["category"] for variant in cu} == {"CU"}


def test_bidding_calibration_uses_nonperfect_turn_budget_mix() -> None:
    variants = task_variants_for("marble_bidding")

    turn_budgets = [variant.loader_kwargs["max_turns"] for variant in variants]
    assert turn_budgets.count(8) == 1
    assert turn_budgets.count(20) == 6
    assert turn_budgets.count(36) == 5


def test_owned_bidding_loader_honors_variant_turn_budget() -> None:
    variant = task_variants_for(
        "marble_bidding",
        cell_id="CU-C-marble_bidding",
    )[0]

    bundle = load_bidding_scenario(**variant.loader_kwargs)

    assert variant.loader_kwargs["max_turns"] == 20
    assert bundle.scenario.max_turns == 20
    assert bundle.scenario.category == "CU"


def test_owned_bidding_loader_builds_seller_centered_graph() -> None:
    bundle = load_bidding_scenario()
    scenario = bundle.scenario

    assert scenario.family_id == "marble_bidding"
    assert scenario.coordination_mode == CoordinationMode.GRAPH
    assert scenario.max_turns == 36

    nodes = scenario.agent_graph.nodes
    roles = [node.role_label for node in nodes]
    assert roles.count("seller") == 1
    assert roles.count("buyer") == 2

    seller_id = next(node.agent_id for node in nodes if node.role_label == "seller")
    buyer_ids = {node.agent_id for node in nodes if node.role_label == "buyer"}
    edges = {(edge.source, edge.target) for edge in scenario.agent_graph.edges}
    for buyer_id in buyer_ids:
        assert (seller_id, buyer_id) in edges
        assert (buyer_id, seller_id) in edges
    assert all(source == seller_id or target == seller_id for source, target in edges)


def test_owned_bidding_loader_exposes_expected_context() -> None:
    bundle = load_bidding_scenario()

    assert bundle.auction_id == "AUC-BID-000"
    assert bundle.resource_profile == "owned_ecosystem_bidding_easy_two_buyer"
    assert bundle.item_id == "BID-LOT-000"
    assert bundle.quantity == 8
    assert bundle.seller_owner_id == "sable_supply_sales"
    assert bundle.buyer_owner_ids == (
        "anchor_procurement",
        "beacon_procurement",
    )
    assert set(bundle.owner_workspaces) == {
        "sable_supply_sales",
        "anchor_procurement",
        "beacon_procurement",
    }
    assert bundle.required_terms == ("delivery_by_2026-06-30", "warranty_12_months")


def test_owned_bidding_opening_names_buyer_agents_and_two_bid_gate() -> None:
    bundle = load_bidding_scenario()
    content = bundle.scenario.opening_message["content"]

    assert "anchor_buyer (`anchor_procurement`)" in content
    assert "beacon_buyer (`beacon_procurement`)" in content
    assert "at least two public bids" in content


def test_owned_bidding_injects_buyer_auction_notices() -> None:
    bundle = load_bidding_scenario()
    notices = bundle.scenario.injected_messages

    assert [notice["to"] for notice in notices] == [
        "anchor_buyer",
        "beacon_buyer",
    ]
    for notice in notices:
        assert notice["from"] == "system"
        assert "read_owned_file" in notice["content"]
        assert "query_owned_table" in notice["content"]
        assert "submit_bid" in notice["content"]


def test_owned_bidding_evaluation_criteria_names_close_tools_and_predicates() -> None:
    bundle = load_bidding_scenario()
    tools = {item["tool_name"] for item in bundle.evaluation_criteria["actions"]}
    assert tools == {
        "submit_bid",
        "seller_award_bid",
        "buyer_confirm_award",
        "record_purchase_order",
        "record_seller_order",
    }

    predicates = {
        item["predicate"] for item in bundle.evaluation_criteria["env_assertions"]
    }
    assert predicates == {
        "bids_from_at_least_two_buyers",
        "winner_bid_was_public_bid",
        "seller_awarded_winning_bid",
        "winning_buyer_confirmed_award",
        "purchase_order_recorded",
        "seller_order_recorded",
        "auction_artifacts_consistent",
        "price_within_owned_bidding_constraints",
        "inventory_available_for_award",
        "required_terms_consistent",
        "resource_backed_bidding_decision",
    }


def test_owned_bidding_evaluation_criteria_resolves_through_registry() -> None:
    from clawsocialarena.eval.predicates.marble_bidding import PREDICATE_REGISTRY

    bundle = load_bidding_scenario()

    for assertion in bundle.evaluation_criteria["env_assertions"]:
        assert assertion["predicate"] in PREDICATE_REGISTRY


@pytest.mark.parametrize("variant", task_variants_for("marble_bidding"))
def test_every_bidding_variant_loads(variant) -> None:
    bundle = load_bidding_scenario(**variant.loader_kwargs)

    assert bundle.auction_id == variant.loader_kwargs["auction_id"]
    assert bundle.seller_owner_id == variant.loader_kwargs["seller_owner"]
    assert bundle.buyer_owner_ids == tuple(variant.loader_kwargs["buyer_owners"])
    assert len(bundle.buyer_owner_ids) >= 2
    assert bundle.seller_minimum_unit_price < max(
        bundle.buyer_budget_ceiling_by_owner.values()
    )
