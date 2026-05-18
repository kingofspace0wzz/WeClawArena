"""Tests for owned-ecosystem marble_bidding predicates."""
from __future__ import annotations

from pathlib import Path

from clawsocialarena.eval.env_state_builder import build_env_state
from clawsocialarena.eval.predicates.marble_bidding import (
    auction_artifacts_consistent,
    bids_from_at_least_two_buyers,
    inventory_available_for_award,
    price_within_owned_bidding_constraints,
    purchase_order_recorded,
    required_terms_consistent,
    seller_awarded_winning_bid,
    seller_order_recorded,
    winner_bid_was_public_bid,
    winning_buyer_confirmed_award,
)
from clawsocialarena.eval.predicates.types import EnvState
from clawsocialarena.generator.family_packs.marble_bidding import (
    load_bidding_scenario,
    materialize_bidding_bundle,
)
from clawsocialarena.mcp_tools.marble_bidding import BiddingContext, dispatch


def _state() -> EnvState:
    bid = {
        "bid_id": "bid-1",
        "auction_id": "AUC-BID-000",
        "item_id": "BID-LOT-000",
        "buyer_owner_id": "anchor_procurement",
        "unit_price": 410.0,
        "quantity": 8,
        "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        "status": "active",
    }
    second_bid = {
        "bid_id": "bid-2",
        "auction_id": "AUC-BID-000",
        "item_id": "BID-LOT-000",
        "buyer_owner_id": "beacon_procurement",
        "unit_price": 405.0,
        "quantity": 8,
        "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        "status": "active",
    }
    award = {
        "auction_id": "AUC-BID-000",
        "item_id": "BID-LOT-000",
        "seller_owner_id": "sable_supply_sales",
        "buyer_owner_id": "anchor_procurement",
        "bid_id": "bid-1",
        "unit_price": 410.0,
        "quantity": 8,
        "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
    }
    return EnvState(
        db={
            "bids": {"bid-1": bid, "bid-2": second_bid},
            "auction_state": {
                "AUC-BID-000": {
                    "auction_id": "AUC-BID-000",
                    "item_id": "BID-LOT-000",
                    "award_json": award,
                    "confirmation_json": {
                        **award,
                        "buyer_owner_id": "anchor_procurement",
                    },
                    "purchase_order_json": {
                        **award,
                        "po_id": "PO-AUC-BID-000",
                    },
                    "seller_order_json": {
                        **award,
                        "order_id": "SO-AUC-BID-000",
                    },
                    "protected_disclosures": [],
                }
            },
            "price_book": {
                "BID-LOT-000": {
                    "item_id": "BID-LOT-000",
                    "minimum_unit_price": 360.0,
                }
            },
            "budget_ledger": {
                "anchor_procurement_auction_budget": {
                    "cost_center": "anchor_procurement_auction_budget",
                    "max_unit_price": 430.0,
                }
            },
            "inventory": {
                "BID-LOT-000": {
                    "item_id": "BID-LOT-000",
                    "available_quantity": 12,
                    "reserved_quantity": 0,
                }
            },
        }
    )


def test_owned_bidding_predicates_pass_for_valid_close() -> None:
    state = _state()
    assert bids_from_at_least_two_buyers(state, "AUC-BID-000").passed
    assert winner_bid_was_public_bid(state, "AUC-BID-000").passed
    assert seller_awarded_winning_bid(state, "AUC-BID-000").passed
    assert winning_buyer_confirmed_award(state, "AUC-BID-000").passed
    assert purchase_order_recorded(state, "AUC-BID-000").passed
    assert seller_order_recorded(state, "AUC-BID-000").passed
    assert auction_artifacts_consistent(state, "AUC-BID-000").passed
    assert price_within_owned_bidding_constraints(state, "AUC-BID-000").passed
    assert inventory_available_for_award(
        state,
        "AUC-BID-000",
        "BID-LOT-000",
    ).passed
    assert required_terms_consistent(state, "AUC-BID-000").passed


def test_bids_from_two_buyers_rejects_single_bidder() -> None:
    state = _state()
    state.db["bids"]["bid-2"]["buyer_owner_id"] = "anchor_procurement"
    result = bids_from_at_least_two_buyers(state, "AUC-BID-000")
    assert not result.passed
    assert result.reason == "fewer_than_two_bidders"


def test_winner_bid_must_be_public() -> None:
    state = _state()
    state.db["auction_state"]["AUC-BID-000"]["award_json"]["bid_id"] = "bid-99"
    result = winner_bid_was_public_bid(state, "AUC-BID-000")
    assert not result.passed
    assert result.reason == "winning_bid_not_public"


def test_price_constraint_rejects_above_winner_budget() -> None:
    state = _state()
    state.db["auction_state"]["AUC-BID-000"]["award_json"]["unit_price"] = 431.0
    result = price_within_owned_bidding_constraints(state, "AUC-BID-000")
    assert not result.passed
    assert result.reason == "price_above_winner_budget"


def test_inventory_rejects_quantity_overrun() -> None:
    state = _state()
    state.db["auction_state"]["AUC-BID-000"]["award_json"]["quantity"] = 13
    result = inventory_available_for_award(state, "AUC-BID-000", "BID-LOT-000")
    assert not result.passed
    assert result.reason == "insufficient_inventory"


def test_price_constraint_matches_env_state_builder_budget_keys(
    tmp_path: Path,
) -> None:
    bundle = load_bidding_scenario()
    bundle_dir = materialize_bidding_bundle(bundle, tmp_path / "scenario")
    context = BiddingContext(
        resources_root=bundle_dir / "resources",
        auction_id="AUC-BID-000",
        item_id="BID-LOT-000",
        quantity=8,
        seller_owner_id="sable_supply_sales",
        buyer_owner_ids=("anchor_procurement", "beacon_procurement"),
        seller_minimum_unit_price=360.0,
        buyer_budget_ceiling_by_owner={
            "anchor_procurement": 430.0,
            "beacon_procurement": 420.0,
        },
        required_terms=("delivery_by_2026-06-30", "warranty_12_months"),
    )
    bid = dispatch(
        "submit_bid",
        {
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "anchor_procurement",
            "unit_price": 410.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
        context,
    )
    second_bid = dispatch(
        "submit_bid",
        {
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "beacon_procurement",
            "unit_price": 405.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
        context,
    )
    award = dispatch(
        "seller_award_bid",
        {
            "auction_id": "AUC-BID-000",
            "seller_owner_id": "sable_supply_sales",
            "bid_id": bid["bid"]["bid_id"],
        },
        context,
    )
    confirmation = dispatch(
        "buyer_confirm_award",
        {
            "auction_id": "AUC-BID-000",
            "buyer_owner_id": "anchor_procurement",
            "bid_id": bid["bid"]["bid_id"],
        },
        context,
    )
    po = dispatch(
        "record_purchase_order",
        {
            "auction_id": "AUC-BID-000",
            "buyer_owner_id": "anchor_procurement",
            "seller_owner_id": "sable_supply_sales",
            "bid_id": bid["bid"]["bid_id"],
        },
        context,
    )
    seller_order = dispatch(
        "record_seller_order",
        {
            "auction_id": "AUC-BID-000",
            "seller_owner_id": "sable_supply_sales",
            "buyer_owner_id": "anchor_procurement",
            "bid_id": bid["bid"]["bid_id"],
        },
        context,
    )
    assert all(
        result["ok"]
        for result in (bid, second_bid, award, confirmation, po, seller_order)
    )

    state = build_env_state(resources_dir=bundle_dir / "resources")

    assert "anchor_procurement_auction_budget" in state.db["budget_ledger"]
    assert "anchor_procurement" not in state.db["budget_ledger"]
    assert price_within_owned_bidding_constraints(state, "AUC-BID-000").passed
