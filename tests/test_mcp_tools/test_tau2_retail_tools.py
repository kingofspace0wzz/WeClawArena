"""Tests for tau2 retail MCP tool handlers.

Validates that each handler operates correctly against a materialized
bundle's per-user SQLite databases, enforces the household
authorization rules from the policy.md excerpt, and returns a dict
the evaluation pipeline can read.

This is the unit-level smoke test for Phase 3c. The Phase 3d batch
will exercise the same handlers end-to-end through the gateway and
the live simulation pipeline.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.gateway.mcp_host import McpHost
from clawsocialarena.generator.family_packs.tau2_retail import (
    load_household_exchange_scenario,
    materialize_household_bundle,
)
from clawsocialarena.mcp_tools.tau2_retail import (
    HouseholdContext,
    TOOL_NAMES,
    dispatch,
    register_tau2_retail_handlers,
)


@pytest.fixture
def household_context(tmp_path: Path) -> HouseholdContext:
    bundle = load_household_exchange_scenario()
    bundle_dir = tmp_path / "scenario"
    materialize_household_bundle(bundle, bundle_dir)
    return HouseholdContext(
        resources_root=bundle_dir / "resources",
        household_id="HH-7",
        primary_owner_id="alice",
        secondary_owner_ids=("bob",),
    )


def test_find_user_id_resolves_household_member(
    household_context: HouseholdContext,
) -> None:
    result = dispatch(
        "find_user_id_by_name_zip",
        {"first_name": "Alice", "zip": "19122"},
        household_context,
    )
    assert result["ok"] is True
    assert result["user_id"] == "alice"
    assert result["household_id"] == "HH-7"


def test_find_user_id_rejects_outsider(
    household_context: HouseholdContext,
) -> None:
    result = dispatch(
        "find_user_id_by_name_zip",
        {"first_name": "Mallory", "zip": "19122"},
        household_context,
    )
    assert result["ok"] is False
    assert result["error"] == "user_not_found"


def test_get_user_details_labels_primary_and_secondary_roles(
    household_context: HouseholdContext,
) -> None:
    primary = dispatch("get_user_details", {"user_id": "alice"}, household_context)
    secondary = dispatch("get_user_details", {"user_id": "bob"}, household_context)
    assert primary["role"] == "primary_account_holder"
    assert secondary["role"] == "secondary_account_holder"


def test_get_order_details_returns_order_for_household_member(
    household_context: HouseholdContext,
) -> None:
    # The materializer seeds the first 3 tau2 orders into the household.
    # We do not know the exact order_ids in advance, so we query the db
    # to pick one.
    import sqlite3

    db = sqlite3.connect(
        household_context.resources_root / "users/alice/db/personal.sqlite"
    )
    try:
        any_order_id = db.execute("SELECT order_id FROM orders LIMIT 1").fetchone()[0]
    finally:
        db.close()

    result = dispatch(
        "get_order_details",
        {"order_id": any_order_id, "caller_id": "alice"},
        household_context,
    )
    assert result["ok"] is True
    assert result["order"]["household_id"] == "HH-7"


def test_exchange_item_requires_primary_holder(
    household_context: HouseholdContext,
) -> None:
    import sqlite3

    db = sqlite3.connect(
        household_context.resources_root / "users/alice/db/personal.sqlite"
    )
    try:
        any_order_id = db.execute("SELECT order_id FROM orders LIMIT 1").fetchone()[0]
    finally:
        db.close()

    secondary = dispatch(
        "exchange_item",
        {
            "order_id": any_order_id,
            "new_item_id": "1656367028",
            "authorizer_id": "bob",
        },
        household_context,
    )
    assert secondary["ok"] is False
    assert secondary["error"] == "authorization_denied"

    primary = dispatch(
        "exchange_item",
        {
            "order_id": any_order_id,
            "new_item_id": "1656367028",
            "authorizer_id": "alice",
        },
        household_context,
    )
    assert primary["ok"] is True
    assert primary["status"] == "finalized"


def test_place_order_enforces_secondary_spending_cap(
    household_context: HouseholdContext,
) -> None:
    secondary_above_cap = dispatch(
        "place_order",
        {
            "order_id": "#W-NEW-001",
            "authorizer_id": "bob",
            "amount_usd": 340,
        },
        household_context,
    )
    assert secondary_above_cap["ok"] is False
    assert secondary_above_cap["error"] == "authorization_denied"
    assert "cap" in secondary_above_cap["reason"]

    secondary_below_cap = dispatch(
        "place_order",
        {
            "order_id": "#W-NEW-002",
            "authorizer_id": "bob",
            "amount_usd": 45,
        },
        household_context,
    )
    assert secondary_below_cap["ok"] is True
    assert secondary_below_cap["status"] == "finalized"

    primary_any_amount = dispatch(
        "place_order",
        {
            "order_id": "#W-NEW-003",
            "authorizer_id": "alice",
            "amount_usd": 5000,
        },
        household_context,
    )
    assert primary_any_amount["ok"] is True


def test_modify_address_blocks_non_household_address(
    household_context: HouseholdContext,
) -> None:
    import sqlite3

    db = sqlite3.connect(
        household_context.resources_root / "users/alice/db/personal.sqlite"
    )
    try:
        any_order_id = db.execute("SELECT order_id FROM orders LIMIT 1").fetchone()[0]
    finally:
        db.close()

    foreign = dispatch(
        "modify_address",
        {
            "order_id": any_order_id,
            "caller_id": "alice",
            "new_address": {
                "street": "1234 Attacker Lane",
                "household_id": "HH-OTHER",
            },
        },
        household_context,
    )
    assert foreign["ok"] is False
    assert foreign["error"] == "address_not_household_owned"

    household_owned = dispatch(
        "modify_address",
        {
            "order_id": any_order_id,
            "caller_id": "alice",
            "new_address": {
                "street": "1 Household Way",
                "household_id": "HH-7",
            },
        },
        household_context,
    )
    assert household_owned["ok"] is True


def test_cancel_pending_order_requires_primary(
    household_context: HouseholdContext,
) -> None:
    # Place a pending order first (bob can place a small order under cap).
    placed = dispatch(
        "place_order",
        {"order_id": "#W-PEND-001", "authorizer_id": "bob", "amount_usd": 30},
        household_context,
    )
    assert placed["ok"]
    # The default place_order writes status='finalized'; for this test
    # we simulate a pending order by direct sqlite manipulation, which
    # mirrors what a richer place_order signature would do later.
    import sqlite3

    db = sqlite3.connect(
        household_context.resources_root / "users/bob/db/personal.sqlite"
    )
    try:
        db.execute(
            "UPDATE orders SET status = 'pending' WHERE order_id = ?",
            ("#W-PEND-001",),
        )
        db.commit()
    finally:
        db.close()

    bob = dispatch(
        "cancel_pending_order",
        {"order_id": "#W-PEND-001", "authorizer_id": "bob"},
        household_context,
    )
    assert bob["ok"] is False
    assert bob["error"] == "authorization_denied"

    alice = dispatch(
        "cancel_pending_order",
        {"order_id": "#W-PEND-001", "authorizer_id": "alice"},
        household_context,
    )
    assert alice["ok"] is True
    assert alice["status"] == "cancelled"


def test_register_tau2_retail_handlers_wires_all_tools(
    household_context: HouseholdContext,
) -> None:
    host = McpHost()
    register_tau2_retail_handlers(host, context=household_context)
    registered = set(host.tools())
    assert set(TOOL_NAMES).issubset(registered)


@pytest.mark.asyncio
async def test_dispatch_through_mcp_host(
    household_context: HouseholdContext,
) -> None:
    """End-to-end: register handlers on a real McpHost and dispatch."""
    host = McpHost()
    register_tau2_retail_handlers(host, context=household_context)
    result = await host.dispatch(
        "find_user_id_by_name_zip",
        {"first_name": "alice", "zip": "19122"},
    )
    assert result["ok"] is True
    assert result["user_id"] == "alice"
