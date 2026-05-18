"""Tests for owned-ecosystem marble_bidding materialization."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.generator.family_packs.marble_bidding import (
    load_bidding_scenario,
    materialize_bidding_bundle,
)


@pytest.fixture
def bundle_dir(tmp_path: Path) -> Path:
    bundle = load_bidding_scenario()
    return materialize_bidding_bundle(bundle, tmp_path / "scenario")


def test_bidding_materializer_writes_top_level_artifacts(bundle_dir: Path) -> None:
    for name in (
        "scenario.json",
        "scenario.gt.json",
        "family_pack_context.json",
        "docker-compose.yml",
    ):
        assert (bundle_dir / name).is_file()


def test_bidding_family_pack_context_carries_owned_ecosystem_fields(
    bundle_dir: Path,
) -> None:
    context = json.loads((bundle_dir / "family_pack_context.json").read_text())
    assert context["auction_id"] == "AUC-BID-000"
    assert context["resource_profile"] == "owned_ecosystem_bidding_easy_two_buyer"
    assert context["item_id"] == "BID-LOT-000"
    assert context["quantity"] == 8
    assert context["seller_owner_id"] == "sable_supply_sales"
    assert context["buyer_owner_ids"] == [
        "anchor_procurement",
        "beacon_procurement",
    ]
    assert context["seller_minimum_unit_price"] == 360.0
    assert context["buyer_budget_ceiling_by_owner"]["anchor_procurement"] == 430.0


def test_bidding_persona_sources_point_to_materialized_files(
    bundle_dir: Path,
) -> None:
    scenario = json.loads((bundle_dir / "scenario.json").read_text())
    for node in scenario["agent_graph"]["nodes"]:
        persona_path = bundle_dir / node["persona_source"]
        assert persona_path.is_file()
        assert persona_path.name.endswith(".system.md")


def test_bidding_personas_name_minimal_close_sequence(bundle_dir: Path) -> None:
    seller_prompt = (bundle_dir / "personas" / "sable_seller.system.md").read_text()
    buyer_prompt = (bundle_dir / "personas" / "anchor_buyer.system.md").read_text()

    assert "seller_award_bid" in seller_prompt
    assert "record_seller_order" in seller_prompt
    assert "at least two public bids" in seller_prompt
    assert "next_required_action" in seller_prompt
    assert "Do not call the auction finalized" in seller_prompt
    assert "if a buyer says the purchase order was recorded" in seller_prompt
    assert "Do not paraphrase required terms" in buyer_prompt
    assert "done" in seller_prompt
    assert "submit_bid" in buyer_prompt
    assert "buyer_confirm_award" in buyer_prompt
    assert "record_purchase_order" in buyer_prompt
    assert "tell the seller to call `record_seller_order`" in buyer_prompt
    assert "retry `record_purchase_order`" in buyer_prompt
    assert "done" in buyer_prompt


def test_bidding_materializer_writes_owned_files(bundle_dir: Path) -> None:
    seller = bundle_dir / "resources" / "agents" / "sable_supply_sales"
    buyer = bundle_dir / "resources" / "agents" / "anchor_procurement"

    assert (seller / "files" / "listing_sheet.md").is_file()
    assert (seller / "files" / "sales_policy.md").is_file()
    assert (seller / "files" / "bid_evaluation_policy.md").is_file()
    assert (buyer / "files" / "purchase_request.md").is_file()
    assert (buyer / "files" / "bidding_policy.md").is_file()
    assert (buyer / "files" / "bid_strategy.md").is_file()


def test_bidding_sqlite_has_tables_for_each_owner(bundle_dir: Path) -> None:
    expected_tables = {
        "sable_supply_sales": {
            "inventory",
            "price_book",
            "bids",
            "auction_state",
            "seller_orders",
        },
        "anchor_procurement": {
            "budget_ledger",
            "bid_authorizations",
            "bids",
            "auction_state",
            "purchase_orders",
        },
        "beacon_procurement": {
            "budget_ledger",
            "bid_authorizations",
            "bids",
            "auction_state",
            "purchase_orders",
        },
    }
    for owner, table_names in expected_tables.items():
        db = bundle_dir / "resources" / "agents" / owner / "db" / "personal.sqlite"
        assert db.is_file()
        with sqlite3.connect(db) as conn:
            actual = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        assert table_names <= actual


def test_bidding_materializer_writes_tool_stubs(bundle_dir: Path) -> None:
    for tool_name in (
        "read_owned_file",
        "query_owned_table",
        "submit_bid",
        "revise_bid",
        "seller_award_bid",
        "buyer_confirm_award",
        "record_purchase_order",
        "record_seller_order",
        "get_auction_status",
        "reveal_protected_field",
    ):
        stub = bundle_dir / "mcp" / f"{tool_name}.json"
        assert stub.is_file()
        payload = json.loads(stub.read_text())
        assert payload["tool_name"] == tool_name
