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


def _seed_buyer_resource_evidence(
    context: BiddingContext,
    *,
    agent_id: str,
    owner_id: str,
) -> None:
    read_result = dispatch(
        "read_owned_file",
        {"_agent_id": agent_id, "owner_id": owner_id, "path": "purchase_request.md"},
        context,
    )
    query_result = dispatch(
        "query_owned_table",
        {"_agent_id": agent_id, "owner_id": owner_id, "table": "budget_ledger"},
        context,
    )
    assert read_result["ok"]
    assert query_result["ok"]


def _seed_seller_resource_evidence(context: BiddingContext) -> None:
    read_result = dispatch(
        "read_owned_file",
        {
            "_agent_id": "sable_seller",
            "owner_id": "sable_supply_sales",
            "path": "listing_sheet.md",
        },
        context,
    )
    query_result = dispatch(
        "query_owned_table",
        {
            "_agent_id": "sable_seller",
            "owner_id": "sable_supply_sales",
            "table": "inventory",
        },
        context,
    )
    assert read_result["ok"]
    assert query_result["ok"]


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


def test_query_owned_table_accepts_table_name_alias(
    bidding_context: BiddingContext,
) -> None:
    table_result = dispatch(
        "query_owned_table",
        {
            "_agent_id": "sable_seller",
            "owner_id": "sable_supply_sales",
            "table_name": "inventory",
        },
        bidding_context,
    )

    assert table_result["ok"]
    assert table_result["table"] == "inventory"


def test_read_owned_file_accepts_file_name_alias(
    bidding_context: BiddingContext,
) -> None:
    file_result = dispatch(
        "read_owned_file",
        {
            "_agent_id": "anchor_buyer",
            "file_name": "purchase_request.md",
        },
        bidding_context,
    )

    assert file_result["ok"]
    assert file_result["owner_id"] == "anchor_procurement"
    assert file_result["path"] == "purchase_request.md"


def test_resource_tools_default_to_role_primary_resource_for_runtime_agent(
    bidding_context: BiddingContext,
) -> None:
    file_result = dispatch(
        "read_owned_file",
        {"_agent_id": "anchor_buyer"},
        bidding_context,
    )
    table_result = dispatch(
        "query_owned_table",
        {"_agent_id": "sable_seller"},
        bidding_context,
    )

    assert file_result["ok"]
    assert file_result["owner_id"] == "anchor_procurement"
    assert file_result["path"] == "purchase_request.md"
    assert table_result["ok"]
    assert table_result["owner_id"] == "sable_supply_sales"
    assert table_result["table"] == "inventory"


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
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="anchor_buyer",
        owner_id="anchor_procurement",
    )
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


def test_submit_bid_requires_buyer_resource_evidence(
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
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
        bidding_context,
    )

    assert result["ok"] is False
    assert result["error"] == "missing_resource_evidence"
    assert result["next_required_action"]["next_tool"] == "read_owned_file"
    assert result["next_required_action"]["resource_steps"][0]["args"] == {
        "owner_id": "anchor_procurement",
        "path": "purchase_request.md",
    }


def test_submit_bid_requires_explicit_canonical_arguments(
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
    assert result["ok"] is False
    assert result["error"] == "missing_required_arguments"
    assert result["missing"] == [
        "auction_id",
        "item_id",
        "buyer_owner_id",
        "unit_price",
        "quantity",
        "terms",
    ]


def test_submit_bid_term_error_returns_exact_required_terms(
    bidding_context: BiddingContext,
) -> None:
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="anchor_buyer",
        owner_id="anchor_procurement",
    )
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
    assert result["error"] == "required_terms_missing"
    assert result["required_terms"] == [
        "delivery_by_2026-06-30",
        "warranty_12_months",
    ]
    assert result["next_required_action"]["next_tool"] == "submit_bid"
    assert "recommended_args" not in result["next_required_action"]
    assert result["next_required_action"]["required_args"] == [
        "auction_id",
        "item_id",
        "buyer_owner_id",
        "unit_price",
        "quantity",
        "terms",
    ]


def test_submit_bid_accepts_exact_terms_as_delimited_string(
    bidding_context: BiddingContext,
) -> None:
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="anchor_buyer",
        owner_id="anchor_procurement",
    )
    result = dispatch(
        "submit_bid",
        {
            "_agent_id": "anchor_buyer",
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "anchor_procurement",
            "unit_price": 410.0,
            "quantity": 8,
            "terms": "delivery_by_2026-06-30;warranty_12_months",
        },
        bidding_context,
    )

    assert result["ok"]
    assert result["bid"]["terms"] == [
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
            "item_id": "BID-000",
            "buyer_owner_id": "anchor_procurement",
            "unit_price": 410.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
        bidding_context,
    )

    assert result["ok"] is False
    assert result["error"] == "auction_or_item_mismatch"
    assert result["expected_item_id"] == "BID-LOT-000"
    assert "recommended_args" not in result["next_required_action"]


def test_authenticated_close_path_requires_explicit_canonical_ids(
    bidding_context: BiddingContext,
) -> None:
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="anchor_buyer",
        owner_id="anchor_procurement",
    )
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="beacon_buyer",
        owner_id="beacon_procurement",
    )
    _seed_seller_resource_evidence(bidding_context)
    anchor_bid = dispatch(
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
    beacon_bid = dispatch(
        "submit_bid",
        {
            "_agent_id": "beacon_buyer",
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "beacon_procurement",
            "unit_price": 405.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
        bidding_context,
    )

    assert anchor_bid["ok"]
    assert beacon_bid["ok"]

    missing_award = dispatch(
        "seller_award_bid",
        {"_agent_id": "sable_seller"},
        bidding_context,
    )
    assert missing_award["ok"] is False
    assert missing_award["error"] == "missing_required_arguments"
    assert missing_award["missing"] == ["auction_id", "seller_owner_id", "bid_id"]

    award = dispatch(
        "seller_award_bid",
        {
            "_agent_id": "sable_seller",
            "auction_id": "AUC-BID-000",
            "seller_owner_id": "sable_supply_sales",
            "bid_id": anchor_bid["bid"]["bid_id"],
        },
        bidding_context,
    )
    winning_bid = award["award"]["bid_id"]

    missing_confirmation = dispatch(
        "buyer_confirm_award",
        {"_agent_id": "anchor_buyer"},
        bidding_context,
    )
    assert missing_confirmation["ok"] is False
    assert missing_confirmation["error"] == "missing_required_arguments"
    assert missing_confirmation["missing"] == ["auction_id", "buyer_owner_id", "bid_id"]

    confirmation = dispatch(
        "buyer_confirm_award",
        {
            "_agent_id": "anchor_buyer",
            "auction_id": "AUC-BID-000",
            "buyer_owner_id": "anchor_procurement",
            "bid_id": anchor_bid["bid"]["bid_id"],
        },
        bidding_context,
    )

    missing_po = dispatch(
        "record_purchase_order",
        {"_agent_id": "anchor_buyer"},
        bidding_context,
    )
    assert missing_po["ok"] is False
    assert missing_po["error"] == "missing_required_arguments"
    assert missing_po["missing"] == [
        "auction_id",
        "buyer_owner_id",
        "seller_owner_id",
        "bid_id",
    ]

    po = dispatch(
        "record_purchase_order",
        {
            "_agent_id": "anchor_buyer",
            "auction_id": "AUC-BID-000",
            "buyer_owner_id": "anchor_procurement",
            "seller_owner_id": "sable_supply_sales",
            "bid_id": anchor_bid["bid"]["bid_id"],
        },
        bidding_context,
    )

    missing_seller_order = dispatch(
        "record_seller_order",
        {"_agent_id": "sable_seller"},
        bidding_context,
    )
    assert missing_seller_order["ok"] is False
    assert missing_seller_order["error"] == "missing_required_arguments"
    assert missing_seller_order["missing"] == [
        "auction_id",
        "seller_owner_id",
        "buyer_owner_id",
        "bid_id",
    ]

    seller_order = dispatch(
        "record_seller_order",
        {
            "_agent_id": "sable_seller",
            "auction_id": "AUC-BID-000",
            "seller_owner_id": "sable_supply_sales",
            "buyer_owner_id": "anchor_procurement",
            "bid_id": anchor_bid["bid"]["bid_id"],
        },
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
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="anchor_buyer",
        owner_id="anchor_procurement",
    )
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
    status = dispatch(
        "get_auction_status",
        {"auction_id": "AUC-BID-000"},
        bidding_context,
    )
    award = dispatch(
        "seller_award_bid",
        {
            "_agent_id": "sable_seller",
            "auction_id": "AUC-BID-000",
            "seller_owner_id": "sable_supply_sales",
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
    assert award["missing_buyer_agent_ids"] == ["beacon_buyer"]
    assert award["missing_buyer_owner_ids"] == ["beacon_procurement"]
    assert award["next_required_action"]["next_tool"] == "submit_bid"
    assert "recommended_args" not in award["next_required_action"]


def test_seller_award_requires_seller_resource_evidence(
    bidding_context: BiddingContext,
) -> None:
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="anchor_buyer",
        owner_id="anchor_procurement",
    )
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="beacon_buyer",
        owner_id="beacon_procurement",
    )
    anchor_bid = dispatch(
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
        "submit_bid",
        {
            "_agent_id": "beacon_buyer",
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "beacon_procurement",
            "unit_price": 405.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
        bidding_context,
    )

    result = dispatch(
        "seller_award_bid",
        {
            "_agent_id": "sable_seller",
            "auction_id": "AUC-BID-000",
            "seller_owner_id": "sable_supply_sales",
            "bid_id": anchor_bid["bid"]["bid_id"],
        },
        bidding_context,
    )

    assert result["ok"] is False
    assert result["error"] == "missing_resource_evidence"
    assert result["next_required_action"]["next_tool"] == "read_owned_file"
    assert result["next_required_action"]["resource_steps"][0]["args"] == {
        "owner_id": "sable_supply_sales",
        "path": "listing_sheet.md",
    }


def test_bid_not_found_feedback_lists_public_bid_ids(
    bidding_context: BiddingContext,
) -> None:
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="anchor_buyer",
        owner_id="anchor_procurement",
    )
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="beacon_buyer",
        owner_id="beacon_procurement",
    )
    _seed_seller_resource_evidence(bidding_context)
    dispatch(
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
        "submit_bid",
        {
            "_agent_id": "beacon_buyer",
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "beacon_procurement",
            "unit_price": 405.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
        bidding_context,
    )

    result = dispatch(
        "seller_award_bid",
        {
            "_agent_id": "sable_seller",
            "auction_id": "AUC-BID-000",
            "seller_owner_id": "sable_supply_sales",
            "bid_id": "anchor_procurement_bid",
        },
        bidding_context,
    )

    assert result["ok"] is False
    assert result["error"] == "bid_not_found"
    assert [bid["bid_id"] for bid in result["public_bids"]] == ["bid-1", "bid-2"]
    assert result["next_required_action"]["next_tool"] == "seller_award_bid"
    assert "recommended_args" not in result["next_required_action"]


def test_close_handoff_feedback_names_next_required_tool(
    bidding_context: BiddingContext,
) -> None:
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="anchor_buyer",
        owner_id="anchor_procurement",
    )
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="beacon_buyer",
        owner_id="beacon_procurement",
    )
    _seed_seller_resource_evidence(bidding_context)
    anchor_bid = dispatch(
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
    beacon_bid = dispatch(
        "submit_bid",
        {
            "_agent_id": "beacon_buyer",
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
            "_agent_id": "sable_seller",
            "auction_id": "AUC-BID-000",
            "seller_owner_id": "sable_supply_sales",
            "bid_id": anchor_bid["bid"]["bid_id"],
        },
        bidding_context,
    )

    assert anchor_bid["ok"]
    assert beacon_bid["ok"]
    assert award["ok"]

    premature_po = dispatch(
        "record_purchase_order",
        {
            "_agent_id": "anchor_buyer",
            "auction_id": "AUC-BID-000",
            "buyer_owner_id": "anchor_procurement",
            "seller_owner_id": "sable_supply_sales",
            "bid_id": award["award"]["bid_id"],
        },
        bidding_context,
    )
    assert premature_po["ok"] is False
    assert premature_po["error"] == "award_not_confirmed"
    assert premature_po["next_required_action"]["next_tool"] == "buyer_confirm_award"
    assert "recommended_args" not in premature_po["next_required_action"]

    confirmation = dispatch(
        "buyer_confirm_award",
        {
            "_agent_id": "anchor_buyer",
            "auction_id": "AUC-BID-000",
            "buyer_owner_id": "anchor_procurement",
            "bid_id": award["award"]["bid_id"],
        },
        bidding_context,
    )
    premature_seller_order = dispatch(
        "record_seller_order",
        {
            "_agent_id": "sable_seller",
            "auction_id": "AUC-BID-000",
            "seller_owner_id": "sable_supply_sales",
            "buyer_owner_id": "anchor_procurement",
            "bid_id": award["award"]["bid_id"],
        },
        bidding_context,
    )
    assert confirmation["ok"]
    assert premature_seller_order["ok"] is False
    assert premature_seller_order["error"] == "purchase_order_missing"
    assert (
        premature_seller_order["next_required_action"]["next_tool"]
        == "record_purchase_order"
    )
    assert "recommended_args" not in premature_seller_order["next_required_action"]

    po = dispatch(
        "record_purchase_order",
        {
            "_agent_id": "anchor_buyer",
            "auction_id": "AUC-BID-000",
            "buyer_owner_id": "anchor_procurement",
            "seller_owner_id": "sable_supply_sales",
            "bid_id": award["award"]["bid_id"],
        },
        bidding_context,
    )
    status = dispatch(
        "get_auction_status",
        {"auction_id": "AUC-BID-000"},
        bidding_context,
    )

    assert po["ok"]
    assert po["next_required_action"]["next_tool"] == "record_seller_order"
    assert "recommended_args" not in po["next_required_action"]
    assert status["next_required_action"] == po["next_required_action"]
    assert status["close_state"] == "purchase_order_recorded"


def test_award_below_seller_minimum_is_denied(
    bidding_context: BiddingContext,
) -> None:
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="anchor_buyer",
        owner_id="anchor_procurement",
    )
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="beacon_buyer",
        owner_id="beacon_procurement",
    )
    _seed_seller_resource_evidence(bidding_context)
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
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="anchor_buyer",
        owner_id="anchor_procurement",
    )
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="beacon_buyer",
        owner_id="beacon_procurement",
    )
    _seed_seller_resource_evidence(bidding_context)
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
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="anchor_buyer",
        owner_id="anchor_procurement",
    )
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
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="anchor_buyer",
        owner_id="anchor_procurement",
    )
    _seed_buyer_resource_evidence(
        bidding_context,
        agent_id="beacon_buyer",
        owner_id="beacon_procurement",
    )
    _seed_seller_resource_evidence(bidding_context)
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
