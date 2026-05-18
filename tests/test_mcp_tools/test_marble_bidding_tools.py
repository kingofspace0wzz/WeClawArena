"""Tests for owned-ecosystem marble_bidding MCP tool handlers."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.gateway.mcp_host import McpHost
from clawsocialarena.generator.family_packs.marble_bidding import (
    load_bidding_scenario,
    materialize_bidding_bundle,
)
from clawsocialarena.mcp_tools.marble_bidding import (
    BiddingContext,
    TOOL_NAMES,
    dispatch,
    register_marble_bidding_handlers,
)


@pytest.fixture
def bidding_context(tmp_path: Path) -> BiddingContext:
    bundle = load_bidding_scenario()
    bundle_dir = materialize_bidding_bundle(bundle, tmp_path / "scenario")
    return BiddingContext(
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
        agent_owner_by_id={
            "sable_seller": "sable_supply_sales",
            "anchor_buyer": "anchor_procurement",
            "beacon_buyer": "beacon_procurement",
        },
    )


def test_read_owned_file_and_query_owned_table(
    bidding_context: BiddingContext,
) -> None:
    file_result = dispatch(
        "read_owned_file",
        {"owner_id": "anchor_procurement", "path": "purchase_request.md"},
        bidding_context,
    )
    assert file_result["ok"]
    assert "BID-LOT-000" in file_result["content"]

    table_result = dispatch(
        "query_owned_table",
        {"owner_id": "sable_supply_sales", "table": "inventory"},
        bidding_context,
    )
    assert table_result["ok"]
    assert any(row["item_id"] == "BID-LOT-000" for row in table_result["rows"])


def test_actor_bound_tools_reject_cross_owner_access(
    bidding_context: BiddingContext,
) -> None:
    read_result = dispatch(
        "read_owned_file",
        {
            "_agent_id": "anchor_buyer",
            "owner_id": "beacon_procurement",
            "path": "purchase_request.md",
        },
        bidding_context,
    )
    table_result = dispatch(
        "query_owned_table",
        {
            "_agent_id": "beacon_buyer",
            "owner_id": "sable_supply_sales",
            "table": "price_book",
        },
        bidding_context,
    )
    assert read_result["ok"] is False
    assert read_result["error"] == "caller_owner_mismatch"
    assert table_result["ok"] is False
    assert table_result["error"] == "caller_owner_mismatch"


def test_submit_and_revise_bid_update_public_log_everywhere(
    bidding_context: BiddingContext,
) -> None:
    first = dispatch(
        "submit_bid",
        {
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "anchor_procurement",
            "unit_price": 400.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
        bidding_context,
    )
    revised = dispatch(
        "revise_bid",
        {
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "anchor_procurement",
            "bid_id": first["bid"]["bid_id"],
            "unit_price": 410.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
        bidding_context,
    )
    assert first["ok"]
    assert revised["ok"]
    status = dispatch(
        "get_auction_status",
        {"auction_id": "AUC-BID-000"},
        bidding_context,
    )
    assert [bid["status"] for bid in status["bids"]] == ["revised"]
    assert status["bids"][0]["unit_price"] == 410.0
    for owner in (
        "sable_supply_sales",
        "anchor_procurement",
        "beacon_procurement",
    ):
        db = bidding_context.resources_root / "agents" / owner / "db" / "personal.sqlite"
        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT unit_price, status FROM bids WHERE bid_id = ?",
                (first["bid"]["bid_id"],),
            ).fetchone()
        assert row == (410.0, "revised")


def test_submit_bid_recovers_caller_owner_and_common_aliases(
    bidding_context: BiddingContext,
) -> None:
    result = dispatch(
        "submit_bid",
        {
            "_agent_id": "beacon_buyer",
            "lot_id": "BID-LOT-000",
            "bid_amount_per_unit": 415.0,
        },
        bidding_context,
    )
    assert result["ok"]
    assert result["bid"]["buyer_owner_id"] == "beacon_procurement"
    assert result["bid"]["item_id"] == "BID-LOT-000"
    assert result["bid"]["quantity"] == 8
    assert result["bid"]["unit_price"] == 415.0
    assert result["bid"]["terms"] == [
        "delivery_by_2026-06-30",
        "warranty_12_months",
    ]


def test_submit_bid_term_error_returns_exact_required_terms(
    bidding_context: BiddingContext,
) -> None:
    result = dispatch(
        "submit_bid",
        {
            "_agent_id": "anchor_buyer",
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "anchor_procurement",
            "unit_price": 410.0,
            "quantity": 8,
            "terms": "delivery by 2026-06-30; 12 month warranty",
        },
        bidding_context,
    )

    assert result["ok"] is False
    assert result["error"] == "invalid_terms"
    assert result["required_terms"] == [
        "delivery_by_2026-06-30",
        "warranty_12_months",
    ]
    assert result["next_required_action"]["next_tool"] == "submit_bid"
    assert result["next_required_action"]["recommended_args"]["terms"] == [
        "delivery_by_2026-06-30",
        "warranty_12_months",
    ]


def test_submit_bid_item_mismatch_returns_canonical_ids(
    bidding_context: BiddingContext,
) -> None:
    result = dispatch(
        "submit_bid",
        {
            "_agent_id": "anchor_buyer",
            "auction_id": "AUC-BID-000",
            "lot_id": "BID-000",
        },
        bidding_context,
    )

    assert result["ok"] is False
    assert result["error"] == "auction_or_item_mismatch"
    assert result["expected_item_id"] == "BID-LOT-000"
    assert result["next_required_action"]["recommended_args"]["item_id"] == (
        "BID-LOT-000"
    )


def test_zero_arg_authenticated_close_path_uses_auction_state_defaults(
    bidding_context: BiddingContext,
) -> None:
    anchor_bid = dispatch(
        "submit_bid",
        {"_agent_id": "anchor_buyer"},
        bidding_context,
    )
    beacon_bid = dispatch(
        "submit_bid",
        {"_agent_id": "beacon_buyer"},
        bidding_context,
    )

    assert anchor_bid["ok"]
    assert beacon_bid["ok"]

    award = dispatch(
        "seller_award_bid",
        {"_agent_id": "sable_seller"},
        bidding_context,
    )
    winning_bid = award["award"]["bid_id"]
    confirmation = dispatch(
        "buyer_confirm_award",
        {"_agent_id": "anchor_buyer"},
        bidding_context,
    )
    po = dispatch(
        "record_purchase_order",
        {"_agent_id": "anchor_buyer"},
        bidding_context,
    )
    seller_order = dispatch(
        "record_seller_order",
        {"_agent_id": "sable_seller"},
        bidding_context,
    )

    assert award["ok"]
    assert winning_bid == anchor_bid["bid"]["bid_id"]
    assert confirmation["ok"]
    assert confirmation["confirmation"]["seller_owner_id"] == "sable_supply_sales"
    assert po["ok"]
    assert seller_order["ok"]


def test_award_requires_two_distinct_public_bidders(
    bidding_context: BiddingContext,
) -> None:
    bid = dispatch(
        "submit_bid",
        {"_agent_id": "anchor_buyer"},
        bidding_context,
    )
    status = dispatch(
        "get_auction_status",
        {"auction_id": "AUC-BID-000"},
        bidding_context,
    )
    award = dispatch(
        "seller_award_bid",
        {
            "_agent_id": "sable_seller",
            "bid_id": bid["bid"]["bid_id"],
        },
        bidding_context,
    )

    assert bid["ok"]
    assert status["close_state"] == "awaiting_bids"
    assert status["next_required_action"]["next_tool"] == "submit_bid"
    assert status["next_required_action"]["instruction"].startswith(
        "At least two buyer owners"
    )
    assert award["ok"] is False
    assert award["error"] == "not_enough_distinct_bidders"
    assert award["distinct_bidder_count"] == 1
    assert award["next_required_action"]["next_tool"] == "submit_bid"


def test_close_handoff_feedback_names_next_required_tool(
    bidding_context: BiddingContext,
) -> None:
    anchor_bid = dispatch(
        "submit_bid",
        {"_agent_id": "anchor_buyer"},
        bidding_context,
    )
    beacon_bid = dispatch(
        "submit_bid",
        {"_agent_id": "beacon_buyer"},
        bidding_context,
    )
    award = dispatch(
        "seller_award_bid",
        {"_agent_id": "sable_seller"},
        bidding_context,
    )

    assert anchor_bid["ok"]
    assert beacon_bid["ok"]
    assert award["ok"]

    premature_po = dispatch(
        "record_purchase_order",
        {"_agent_id": "anchor_buyer"},
        bidding_context,
    )
    assert premature_po["ok"] is False
    assert premature_po["error"] == "award_not_confirmed"
    assert premature_po["next_required_action"]["next_tool"] == "buyer_confirm_award"
    assert premature_po["next_required_action"]["recommended_args"] == {
        "auction_id": "AUC-BID-000",
        "buyer_owner_id": "anchor_procurement",
        "bid_id": award["award"]["bid_id"],
    }

    confirmation = dispatch(
        "buyer_confirm_award",
        {"_agent_id": "anchor_buyer"},
        bidding_context,
    )
    premature_seller_order = dispatch(
        "record_seller_order",
        {"_agent_id": "sable_seller"},
        bidding_context,
    )
    assert confirmation["ok"]
    assert premature_seller_order["ok"] is False
    assert premature_seller_order["error"] == "purchase_order_missing"
    assert (
        premature_seller_order["next_required_action"]["next_tool"]
        == "record_purchase_order"
    )
    assert premature_seller_order["next_required_action"]["recommended_args"] == {
        "auction_id": "AUC-BID-000",
        "buyer_owner_id": "anchor_procurement",
        "seller_owner_id": "sable_supply_sales",
        "bid_id": award["award"]["bid_id"],
    }

    po = dispatch(
        "record_purchase_order",
        {"_agent_id": "anchor_buyer"},
        bidding_context,
    )
    status = dispatch(
        "get_auction_status",
        {"auction_id": "AUC-BID-000"},
        bidding_context,
    )

    assert po["ok"]
    assert po["next_required_action"]["next_tool"] == "record_seller_order"
    assert po["next_required_action"]["recommended_args"] == {
        "auction_id": "AUC-BID-000",
        "seller_owner_id": "sable_supply_sales",
        "buyer_owner_id": "anchor_procurement",
        "bid_id": award["award"]["bid_id"],
    }
    assert status["next_required_action"] == po["next_required_action"]
    assert status["close_state"] == "purchase_order_recorded"


def test_award_below_seller_minimum_is_denied(
    bidding_context: BiddingContext,
) -> None:
    bid = dispatch(
        "submit_bid",
        {
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "anchor_procurement",
            "unit_price": 350.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
        bidding_context,
    )
    dispatch(
        "submit_bid",
        {
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "beacon_procurement",
            "unit_price": 410.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
        bidding_context,
    )
    result = dispatch(
        "seller_award_bid",
        {
            "auction_id": "AUC-BID-000",
            "seller_owner_id": "sable_supply_sales",
            "bid_id": bid["bid"]["bid_id"],
        },
        bidding_context,
    )
    assert result["ok"] is False
    assert result["error"] == "price_below_seller_minimum"


def test_confirmation_above_buyer_budget_is_denied(
    bidding_context: BiddingContext,
) -> None:
    bid = dispatch(
        "submit_bid",
        {
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "anchor_procurement",
            "unit_price": 431.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
        bidding_context,
    )
    dispatch(
        "submit_bid",
        {
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "beacon_procurement",
            "unit_price": 410.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
        bidding_context,
    )
    dispatch(
        "seller_award_bid",
        {
            "auction_id": "AUC-BID-000",
            "seller_owner_id": "sable_supply_sales",
            "bid_id": bid["bid"]["bid_id"],
        },
        bidding_context,
    )
    result = dispatch(
        "buyer_confirm_award",
        {
            "auction_id": "AUC-BID-000",
            "buyer_owner_id": "anchor_procurement",
            "bid_id": bid["bid"]["bid_id"],
        },
        bidding_context,
    )
    assert result["ok"] is False
    assert result["error"] == "price_above_buyer_budget"


def test_wrong_agent_cannot_confirm_for_winning_buyer(
    bidding_context: BiddingContext,
) -> None:
    bid = dispatch(
        "submit_bid",
        {
            "_agent_id": "anchor_buyer",
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "anchor_procurement",
            "unit_price": 410.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
        bidding_context,
    )
    dispatch(
        "seller_award_bid",
        {
            "_agent_id": "sable_seller",
            "auction_id": "AUC-BID-000",
            "seller_owner_id": "sable_supply_sales",
            "bid_id": bid["bid"]["bid_id"],
        },
        bidding_context,
    )
    confirmation = dispatch(
        "buyer_confirm_award",
        {
            "_agent_id": "beacon_buyer",
            "auction_id": "AUC-BID-000",
            "buyer_owner_id": "anchor_procurement",
            "bid_id": bid["bid"]["bid_id"],
        },
        bidding_context,
    )
    assert confirmation["ok"] is False
    assert confirmation["error"] == "caller_owner_mismatch"


def test_owned_bidding_close_records_artifacts_everywhere(
    bidding_context: BiddingContext,
) -> None:
    bid1 = dispatch(
        "submit_bid",
        {
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "anchor_procurement",
            "unit_price": 410.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
        bidding_context,
    )
    dispatch(
        "submit_bid",
        {
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "beacon_procurement",
            "unit_price": 405.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
        bidding_context,
    )
    award = dispatch(
        "seller_award_bid",
        {
            "auction_id": "AUC-BID-000",
            "seller_owner_id": "sable_supply_sales",
            "bid_id": bid1["bid"]["bid_id"],
        },
        bidding_context,
    )
    confirmation = dispatch(
        "buyer_confirm_award",
        {
            "auction_id": "AUC-BID-000",
            "buyer_owner_id": "anchor_procurement",
            "bid_id": bid1["bid"]["bid_id"],
        },
        bidding_context,
    )
    po = dispatch(
        "record_purchase_order",
        {
            "auction_id": "AUC-BID-000",
            "buyer_owner_id": "anchor_procurement",
            "seller_owner_id": "sable_supply_sales",
            "bid_id": bid1["bid"]["bid_id"],
        },
        bidding_context,
    )
    seller_order = dispatch(
        "record_seller_order",
        {
            "auction_id": "AUC-BID-000",
            "seller_owner_id": "sable_supply_sales",
            "buyer_owner_id": "anchor_procurement",
            "bid_id": bid1["bid"]["bid_id"],
        },
        bidding_context,
    )

    assert award["ok"]
    assert confirmation["ok"]
    assert po["ok"]
    assert seller_order["ok"]

    for owner in (
        "sable_supply_sales",
        "anchor_procurement",
        "beacon_procurement",
    ):
        db = bidding_context.resources_root / "agents" / owner / "db" / "personal.sqlite"
        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT award_json, confirmation_json, purchase_order_json, "
                "seller_order_json FROM auction_state WHERE auction_id = ?",
                ("AUC-BID-000",),
            ).fetchone()
        assert all(value is not None for value in row)


def test_reveal_protected_field_records_disclosure(
    bidding_context: BiddingContext,
) -> None:
    result = dispatch(
        "reveal_protected_field",
        {
            "auction_id": "AUC-BID-000",
            "owner_id": "anchor_procurement",
            "field_name": "budget_ceiling",
            "value": 430.0,
            "recipient_owner_id": "sable_supply_sales",
        },
        bidding_context,
    )
    assert result["ok"]
    assert result["status"] == "disclosed"
    status = dispatch(
        "get_auction_status",
        {"auction_id": "AUC-BID-000"},
        bidding_context,
    )
    assert status["protected_disclosures"] == [
        {
            "owner_id": "anchor_procurement",
            "field_name": "budget_ceiling",
            "value": 430.0,
            "recipient_owner_id": "sable_supply_sales",
        }
    ]
    for owner in (
        "sable_supply_sales",
        "anchor_procurement",
        "beacon_procurement",
    ):
        db = bidding_context.resources_root / "agents" / owner / "db" / "personal.sqlite"
        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT protected_disclosures FROM auction_state WHERE auction_id = ?",
                ("AUC-BID-000",),
            ).fetchone()
        assert json.loads(row[0]) == status["protected_disclosures"]


def test_register_bidding_handlers_wires_all_tools(
    bidding_context: BiddingContext,
) -> None:
    host = McpHost()
    register_marble_bidding_handlers(host, context=bidding_context)
    assert set(TOOL_NAMES).issubset(set(host.tools()))


@pytest.mark.asyncio
async def test_dispatch_through_mcp_host(bidding_context: BiddingContext) -> None:
    host = McpHost()
    register_marble_bidding_handlers(host, context=bidding_context)
    result = await host.dispatch(
        "get_auction_status",
        {"auction_id": "AUC-BID-000"},
    )
    assert result["ok"]
