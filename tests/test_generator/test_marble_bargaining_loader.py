"""Tests for the owned-ecosystem marble_bargaining family pack loader."""
from __future__ import annotations

import pytest

from clawsocialarena.generator.family_packs.marble_bargaining import (
    MarbleBargainingLoader,
    load_bargaining_scenario,
)
from clawsocialarena.generator.phase5_task_variants import task_variants_for
from clawsocialarena.scenario.models import CoordinationMode


def test_bargaining_task_variants_are_owned_ecosystem_tasks() -> None:
    variants = task_variants_for("marble_bargaining")
    assert len(variants) == 24

    by_transaction = {
        variant.loader_kwargs["transaction_id"]: variant.loader_kwargs
        for variant in variants
    }
    assert {
        "TXN-OE-001",
        "TXN-OE-101",
        "TXN-OE-102",
        "TXN-OE-103",
    } <= set(by_transaction)

    assert by_transaction["TXN-OE-001"]["resource_profile"] == (
        "owned_ecosystem_procurement"
    )
    assert by_transaction["TXN-OE-101"]["resource_profile"] == (
        "owned_ecosystem_inventory_allocation"
    )
    assert by_transaction["TXN-OE-102"]["resource_profile"] == (
        "owned_ecosystem_shipping_terms"
    )
    assert by_transaction["TXN-OE-103"]["resource_profile"] == (
        "owned_ecosystem_renewal_addon"
    )

    assert by_transaction["TXN-OE-101"]["buyer_owner"] == "harborview_procurement"
    assert by_transaction["TXN-OE-101"]["seller_owner"] == "northstar_sales"
    assert by_transaction["TXN-OE-101"]["approver_owner"] == "harborview_finance"

    assert by_transaction["TXN-OE-102"]["buyer_owner"] == "evergreen_procurement"
    assert by_transaction["TXN-OE-102"]["seller_owner"] == "atlas_supply_sales"
    assert by_transaction["TXN-OE-102"]["approver_owner"] == "evergreen_compliance"

    assert by_transaction["TXN-OE-103"]["buyer_owner"] == "meridian_it_procurement"
    assert by_transaction["TXN-OE-103"]["seller_owner"] == "omniworks_account_sales"
    assert by_transaction["TXN-OE-103"]["approver_owner"] == (
        "meridian_vendor_management"
    )


def test_bargaining_cell_task_slices_do_not_clone_each_other() -> None:
    cu = task_variants_for(
        "marble_bargaining",
        cell_id="CU-A-marble_bargaining",
    )
    cm = task_variants_for(
        "marble_bargaining",
        cell_id="CM-A-marble_bargaining",
    )

    assert len(cu) == 12
    assert len(cm) == 12
    for task_index in range(12):
        assert cu[task_index].task_index == task_index
        assert cm[task_index].task_index == task_index
        assert cu[task_index].loader_kwargs["transaction_id"] != cm[
            task_index
        ].loader_kwargs["transaction_id"]
        assert cu[task_index].loader_kwargs["buyer_owner"] != cm[
            task_index
        ].loader_kwargs["buyer_owner"]


def test_expansion_seeds_load_with_task_specific_predicates() -> None:
    variants = task_variants_for("marble_bargaining")
    by_transaction = {
        variant.loader_kwargs["transaction_id"]: variant.loader_kwargs
        for variant in variants
    }

    expectations = {
        "TXN-OE-101": "inventory_allocation_feasible",
        "TXN-OE-102": "shipping_terms_consistent",
        "TXN-OE-103": "prior_contract_terms_consistent",
    }
    expected_transactions = set(expectations)
    assert expected_transactions <= set(by_transaction)

    for transaction_id, predicate in expectations.items():
        bundle = load_bargaining_scenario(**by_transaction[transaction_id])
        predicates = {
            assertion["predicate"]
            for assertion in bundle.evaluation_criteria["env_assertions"]
        }
        assert predicate in predicates
        assert bundle.scenario.max_turns == 36
        assert set(bundle.owner_workspaces) == {
            bundle.buyer_owner_id,
            bundle.seller_owner_id,
            bundle.approver_owner_id,
        }


def test_owned_ecosystem_loader_builds_three_owner_graph() -> None:
    bundle = load_bargaining_scenario()

    assert bundle.scenario.family_id == "marble_bargaining"
    assert bundle.scenario.coordination_mode == CoordinationMode.GRAPH
    assert bundle.scenario.max_turns == 36
    assert bundle.resource_profile == "owned_ecosystem_procurement"
    assert bundle.transaction_id == "TXN-OE-001"

    nodes = {node.role_label: node for node in bundle.scenario.agent_graph.nodes}
    assert set(nodes) == {"buyer", "seller", "finance_approver"}
    assert nodes["buyer"].owner_id == "acme_procurement"
    assert nodes["seller"].owner_id == "northstar_sales"
    assert nodes["finance_approver"].owner_id == "acme_finance"

    predicates = {
        assertion["predicate"]
        for assertion in bundle.evaluation_criteria["env_assertions"]
    }
    assert predicates == {
        "purchase_order_recorded",
        "seller_order_recorded",
        "approval_log_recorded",
        "transaction_artifacts_consistent",
        "price_within_owned_constraints",
    }


def test_phase_schedule_tracks_family_turn_cap() -> None:
    bundle = load_bargaining_scenario()
    assert bundle.phase_schedule[-1]["phase"] == "agreement"
    assert bundle.phase_schedule[-1]["end_turn"] == bundle.scenario.max_turns


def test_initial_state_carries_owned_transaction_fields() -> None:
    bundle = load_bargaining_scenario()
    assert bundle.scenario.initial_state["transaction_id"] == "TXN-OE-001"
    assert bundle.scenario.initial_state["item_id"] == "PRINTER-BUNDLE-12"
    assert bundle.scenario.initial_state["quantity"] == 12
    assert bundle.scenario.initial_state["target_price"] == 795.0


def test_loader_kwargs_override_owned_fields() -> None:
    bundle = load_bargaining_scenario(
        transaction_id="TXN-OE-999",
        item_id="ALT-ITEM",
        quantity=3,
        target_price=88.5,
    )
    assert bundle.transaction_id == "TXN-OE-999"
    assert bundle.item_id == "ALT-ITEM"
    assert bundle.quantity == 3
    assert bundle.target_price == 88.5


def test_loader_keeps_marble_source_read_available() -> None:
    loader = MarbleBargainingLoader()
    if not (loader._root / "bargaining_main.jsonl").is_file():
        pytest.skip("MARBLE source checkout is not available")
    tasks = loader._load_tasks()
    assert tasks
    assert "agents" in tasks[0]
