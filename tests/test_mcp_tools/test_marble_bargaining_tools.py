"""Tests for marble_bargaining MCP tool handlers."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.gateway.mcp_host import McpHost
from clawsocialarena.generator.family_packs.marble_bargaining import (
    load_bargaining_scenario,
    materialize_bargaining_bundle,
)
from clawsocialarena.mcp_tools.marble_bargaining import (
    BargainingContext,
    TOOL_NAMES,
    dispatch,
    register_marble_bargaining_handlers,
)


@pytest.fixture
def bargaining_context(tmp_path: Path) -> BargainingContext:
    bundle = load_bargaining_scenario()
    bundle_dir = tmp_path / "scenario"
    materialize_bargaining_bundle(bundle, bundle_dir)
    return BargainingContext(
        resources_root=bundle_dir / "resources",
        item_id="ITEM-7",
        buyer_owner_id="alice",
        seller_owner_id="bob",
        market_reference_price=bundle.market_reference_price,
        buyer_budget_ceiling=bundle.buyer_budget_ceiling,
        seller_reservation=bundle.seller_reservation,
    )


def test_get_market_reference_returns_seeded_price(
    bargaining_context: BargainingContext,
) -> None:
    result = dispatch("get_market_reference", {"item_id": "ITEM-7"}, bargaining_context)
    assert result["ok"]
    assert result["market_reference_price"] == bargaining_context.market_reference_price


def test_offer_and_counter_append_to_offers_log(
    bargaining_context: BargainingContext,
) -> None:
    dispatch(
        "offer_price",
        {"item_id": "ITEM-7", "poster_id": "alice", "price": 45.0},
        bargaining_context,
    )
    dispatch(
        "counter_offer",
        {"item_id": "ITEM-7", "poster_id": "bob", "price": 55.0},
        bargaining_context,
    )
    buyer_db = bargaining_context.resources_root / "agents" / "alice" / "db" / "personal.sqlite"
    with sqlite3.connect(buyer_db) as conn:
        row = conn.execute("SELECT offers FROM items WHERE item_id = 'ITEM-7'").fetchone()
    import json

    offers = json.loads(row[0])
    assert len(offers) == 2
    kinds = {o["kind"] for o in offers}
    assert kinds == {"offer", "counter"}


def test_accept_above_buyer_budget_denied(
    bargaining_context: BargainingContext,
) -> None:
    above = bargaining_context.buyer_budget_ceiling + 5.0
    result = dispatch(
        "accept_offer",
        {"item_id": "ITEM-7", "accepter_id": "alice", "price": above},
        bargaining_context,
    )
    assert result["ok"] is False
    assert result["error"] == "price_above_buyer_budget"


def test_accept_below_seller_reservation_denied(
    bargaining_context: BargainingContext,
) -> None:
    below = bargaining_context.seller_reservation - 5.0
    result = dispatch(
        "accept_offer",
        {"item_id": "ITEM-7", "accepter_id": "bob", "price": below},
        bargaining_context,
    )
    assert result["ok"] is False
    assert result["error"] == "price_below_seller_reservation"


def test_accept_within_window_records_agreement(
    bargaining_context: BargainingContext,
) -> None:
    agreed_price = bargaining_context.market_reference_price
    result = dispatch(
        "accept_offer",
        {"item_id": "ITEM-7", "accepter_id": "alice", "price": agreed_price},
        bargaining_context,
    )
    assert result["ok"]
    assert result["agreement"]["price"] == agreed_price
    # Both agents' DBs should now show the agreement.
    for owner in ("alice", "bob"):
        db = bargaining_context.resources_root / "agents" / owner / "db" / "personal.sqlite"
        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT agreement FROM items WHERE item_id = 'ITEM-7'"
            ).fetchone()
            assert row[0] is not None, f"agreement missing from {owner}'s db"


def test_reveal_constraint_records_privacy_leak(
    bargaining_context: BargainingContext,
) -> None:
    result = dispatch(
        "reveal_constraint",
        {
            "item_id": "ITEM-7",
            "revealer_id": "alice",
            "kind": "budget_ceiling",
            "value": bargaining_context.buyer_budget_ceiling,
        },
        bargaining_context,
    )
    assert result["ok"]
    db = bargaining_context.resources_root / "agents" / "bob" / "db" / "personal.sqlite"
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT revealed_constraints FROM items WHERE item_id = 'ITEM-7'"
        ).fetchone()
    import json

    leaks = json.loads(row[0])
    assert len(leaks) == 1
    assert leaks[0]["kind"] == "budget_ceiling"


def test_register_bargaining_handlers_wires_all_tools(
    bargaining_context: BargainingContext,
) -> None:
    host = McpHost()
    register_marble_bargaining_handlers(host, context=bargaining_context)
    registered = set(host.tools())
    assert set(TOOL_NAMES).issubset(registered)


@pytest.mark.asyncio
async def test_dispatch_through_mcp_host(
    bargaining_context: BargainingContext,
) -> None:
    host = McpHost()
    register_marble_bargaining_handlers(host, context=bargaining_context)
    result = await host.dispatch("get_market_reference", {"item_id": "ITEM-7"})
    assert result["ok"]
