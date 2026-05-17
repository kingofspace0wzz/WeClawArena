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

import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.gateway.mcp_host import McpHost
from clawsocialarena.generator.family_packs.tau2_retail import (
    load_household_exchange_scenario,
    materialize_household_bundle,
)
from clawsocialarena.mcp_tools.tau2_retail import (
    HouseholdContext,
    RetailSessionContext,
    TOOL_NAMES,
    dispatch,
    register_tau2_retail_handlers,
)


# ---------------------------------------------------------------------------
# Shared-account context helpers
# ---------------------------------------------------------------------------

def _setup_shared_account_context(tmp_path: Path) -> RetailSessionContext:
    """Minimal shared_account context with alice (primary) and bob (secondary)."""
    resources = tmp_path / "resources"
    # Create alice's and bob's personal DBs.
    for owner in ("alice", "bob"):
        db_dir = resources / "users" / owner / "db"
        db_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_dir / "personal.sqlite")
        try:
            conn.execute(
                "CREATE TABLE orders ("
                "order_id TEXT PRIMARY KEY, household_id TEXT NOT NULL, "
                "owner_visible TEXT NOT NULL, status TEXT NOT NULL, "
                "payment_authorized_by TEXT, shipping_address TEXT)"
            )
            conn.commit()
        finally:
            conn.close()
    # Create shared orders DB.
    shared_dir = resources / "shared" / "HH-7"
    shared_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(shared_dir / "shared_account_orders.sqlite")
    try:
        conn.execute(
            "CREATE TABLE orders ("
            "order_id TEXT PRIMARY KEY, placed_by_owner_id TEXT, "
            "payment_authorized_by TEXT, shipping_address_id TEXT, "
            "status TEXT, total REAL)"
        )
        conn.commit()
    finally:
        conn.close()
    return RetailSessionContext(
        resources_root=resources,
        archetype="shared_account",
        household_id="HH-7",
        primary_owner_id="alice",
        secondary_owner_ids=("bob",),
        shared_account_id="HH-7",
    )


def _seed_overcap_pending_order(
    context: RetailSessionContext, order_id: str
) -> None:
    """Insert a pending order into the shared orders DB."""
    db = sqlite3.connect(
        context.resources_root / "shared" / context.shared_account_id
        / "shared_account_orders.sqlite"
    )
    try:
        db.execute(
            "INSERT INTO orders (order_id, placed_by_owner_id, status, total) "
            "VALUES (?, 'bob', 'pending', 250.0)",
            (order_id,),
        )
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Cross-account context helpers
# ---------------------------------------------------------------------------

def _setup_cross_account_context(tmp_path: Path) -> RetailSessionContext:
    """Minimal cross_account context: carol (sender) -> dave (recipient)."""
    resources = tmp_path / "resources"
    for owner in ("carol", "dave"):
        db_dir = resources / "users" / owner / "db"
        db_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_dir / "personal.sqlite")
        try:
            conn.execute(
                "CREATE TABLE incoming_gift_requests ("
                "request_id TEXT PRIMARY KEY, consent_status TEXT, "
                "payment_share_status TEXT, requested_address_id TEXT)"
            )
            conn.execute(
                "CREATE TABLE gift_orders ("
                "order_id TEXT PRIMARY KEY, status TEXT, "
                "payment_share_state TEXT)"
            )
            conn.commit()
        finally:
            conn.close()
    return RetailSessionContext(
        resources_root=resources,
        archetype="cross_account",
        sender_owner_id="carol",
        recipient_owner_id="dave",
    )


def _seed_gift_request(
    context: RetailSessionContext, request_id: str
) -> None:
    """Insert a pending gift request row into the recipient's DB."""
    db = sqlite3.connect(
        context.resources_root / "users" / context.recipient_owner_id
        / "db" / "personal.sqlite"
    )
    try:
        db.execute(
            "INSERT INTO incoming_gift_requests "
            "(request_id, consent_status, payment_share_status) "
            "VALUES (?, 'pending', 'pending')",
            (request_id,),
        )
        db.commit()
    finally:
        db.close()


def _seed_gift_order(
    context: RetailSessionContext, order_id: str
) -> None:
    """Insert a gift order row into the sender's DB."""
    db = sqlite3.connect(
        context.resources_root / "users" / context.sender_owner_id
        / "db" / "personal.sqlite"
    )
    try:
        db.execute(
            "INSERT INTO gift_orders (order_id, status, payment_share_state) "
            "VALUES (?, 'active', 'pending')",
            (order_id,),
        )
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Hub-aggregator context helpers
# ---------------------------------------------------------------------------

def _setup_hub_aggregator_context(tmp_path: Path) -> RetailSessionContext:
    """Minimal hub_aggregator context: eve (hub), frank + grace (spokes)."""
    resources = tmp_path / "resources"
    for owner in ("eve", "frank", "grace"):
        db_dir = resources / "users" / owner / "db"
        db_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_dir / "personal.sqlite")
        try:
            conn.execute(
                "CREATE TABLE my_request ("
                "item_id TEXT, qty INTEGER, target_price REAL, "
                "preferred_options TEXT, delivery_address_id TEXT)"
            )
            conn.commit()
        finally:
            conn.close()
    shared_dir = resources / "shared" / "HUB-1"
    shared_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(shared_dir / "shared_account_orders.sqlite")
    try:
        conn.execute(
            "CREATE TABLE orders ("
            "order_id TEXT PRIMARY KEY, placed_by_owner_id TEXT, "
            "payment_authorized_by TEXT, shipping_address_id TEXT, "
            "status TEXT, total REAL)"
        )
        conn.execute(
            "CREATE TABLE order_line_items ("
            "order_id TEXT, item_id TEXT, qty INTEGER, "
            "originating_spoke_id TEXT)"
        )
        conn.commit()
    finally:
        conn.close()
    return RetailSessionContext(
        resources_root=resources,
        archetype="hub_aggregator",
        hub_owner_id="eve",
        spoke_owner_ids=("frank", "grace"),
        shared_account_id="HUB-1",
    )


# ---------------------------------------------------------------------------
# Store-rep-dyad context helpers
# ---------------------------------------------------------------------------

def _setup_store_rep_dyad_context(tmp_path: Path) -> RetailSessionContext:
    """Minimal store_rep_dyad context: hank (customer), iris (store rep)."""
    resources = tmp_path / "resources"
    for owner in ("hank", "iris"):
        db_dir = resources / "users" / owner / "db"
        db_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_dir / "personal.sqlite")
        try:
            conn.execute(
                "CREATE TABLE retail_orders ("
                "order_id TEXT PRIMARY KEY, status TEXT)"
            )
            conn.commit()
        finally:
            conn.close()
    return RetailSessionContext(
        resources_root=resources,
        archetype="store_rep_dyad",
        customer_owner_id="hank",
        store_rep_owner_id="iris",
    )


def _seed_retail_order(
    context: RetailSessionContext, order_id: str, owner_id: str
) -> None:
    """Insert a retail order row into owner_id's personal DB."""
    db = sqlite3.connect(
        context.resources_root / "users" / owner_id / "db" / "personal.sqlite"
    )
    try:
        db.execute(
            "INSERT INTO retail_orders (order_id, status) VALUES (?, 'active')",
            (order_id,),
        )
        db.commit()
    finally:
        db.close()


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


# ---------------------------------------------------------------------------
# Tests for primary_approve_overcap
# ---------------------------------------------------------------------------

def test_primary_approve_overcap_rejects_non_primary(tmp_path: Path) -> None:
    context = _setup_shared_account_context(tmp_path)
    _seed_overcap_pending_order(context, order_id="#W-OVERCAP-1")
    result = dispatch(
        "primary_approve_overcap",
        {
            "order_id": "#W-OVERCAP-1",
            "approver_owner_id": "bob",
            "authorization_code": "HH-7-PRIMARY-APPROVAL-9F2C",
        },
        context,
    )
    assert result["ok"] is False
    assert result["error"] == "approver_is_not_primary"


def test_primary_approve_overcap_records_approval_for_primary(tmp_path: Path) -> None:
    context = _setup_shared_account_context(tmp_path)
    _seed_overcap_pending_order(context, order_id="#W-OVERCAP-1")
    result = dispatch(
        "primary_approve_overcap",
        {
            "order_id": "#W-OVERCAP-1",
            "approver_owner_id": "alice",
            "authorization_code": "HH-7-PRIMARY-APPROVAL-9F2C",
        },
        context,
    )
    assert result["ok"] is True
    assert result["approved_by"] == "alice"
    assert result["authorization_code_cited"] == "HH-7-PRIMARY-APPROVAL-9F2C"


# ---------------------------------------------------------------------------
# Tests for grant_address_consent
# ---------------------------------------------------------------------------

def test_grant_address_consent_rejects_wrong_recipient(tmp_path: Path) -> None:
    context = _setup_cross_account_context(tmp_path)
    _seed_gift_request(context, request_id="#W-GIFT-1")
    result = dispatch(
        "grant_address_consent",
        {
            "order_id": "#W-GIFT-1",
            "address_id": "ADDR-42",
            "consenting_owner_id": "carol",
        },
        context,
    )
    assert result["ok"] is False
    assert result["error"] == "consenting_owner_not_recipient"


def test_grant_address_consent_succeeds_for_recipient(tmp_path: Path) -> None:
    context = _setup_cross_account_context(tmp_path)
    _seed_gift_request(context, request_id="#W-GIFT-1")
    result = dispatch(
        "grant_address_consent",
        {
            "order_id": "#W-GIFT-1",
            "address_id": "ADDR-42",
            "consenting_owner_id": "dave",
        },
        context,
    )
    assert result["ok"] is True
    assert result["address_id"] == "ADDR-42"
    assert result["consenting_owner_id"] == "dave"


# ---------------------------------------------------------------------------
# Tests for grant_payment_share_consent
# ---------------------------------------------------------------------------

def test_grant_payment_share_consent_rejects_wrong_recipient(tmp_path: Path) -> None:
    context = _setup_cross_account_context(tmp_path)
    _seed_gift_request(context, request_id="#W-GIFT-2")
    result = dispatch(
        "grant_payment_share_consent",
        {
            "order_id": "#W-GIFT-2",
            "payment_method_id": "PM-99",
            "consenting_owner_id": "carol",
        },
        context,
    )
    assert result["ok"] is False
    assert result["error"] == "consenting_owner_not_recipient"


def test_grant_payment_share_consent_succeeds_for_recipient(tmp_path: Path) -> None:
    context = _setup_cross_account_context(tmp_path)
    _seed_gift_request(context, request_id="#W-GIFT-2")
    result = dispatch(
        "grant_payment_share_consent",
        {
            "order_id": "#W-GIFT-2",
            "payment_method_id": "PM-99",
            "consenting_owner_id": "dave",
        },
        context,
    )
    assert result["ok"] is True
    assert result["payment_method_id"] == "PM-99"


# ---------------------------------------------------------------------------
# Tests for confirm_return_payment_routing
# ---------------------------------------------------------------------------

def test_confirm_return_payment_routing_rejects_non_sender(tmp_path: Path) -> None:
    context = _setup_cross_account_context(tmp_path)
    _seed_gift_order(context, order_id="#W-RETURN-1")
    result = dispatch(
        "confirm_return_payment_routing",
        {
            "order_id": "#W-RETURN-1",
            "payment_method_id": "PM-77",
            "consenting_owner_id": "dave",
        },
        context,
    )
    assert result["ok"] is False
    assert result["error"] == "consenting_owner_not_sender"


def test_confirm_return_payment_routing_succeeds_for_sender(tmp_path: Path) -> None:
    context = _setup_cross_account_context(tmp_path)
    _seed_gift_order(context, order_id="#W-RETURN-1")
    result = dispatch(
        "confirm_return_payment_routing",
        {
            "order_id": "#W-RETURN-1",
            "payment_method_id": "PM-77",
            "consenting_owner_id": "carol",
        },
        context,
    )
    assert result["ok"] is True
    assert result["payment_method_id"] == "PM-77"


# ---------------------------------------------------------------------------
# Tests for place_aggregated_order
# ---------------------------------------------------------------------------

def test_place_aggregated_order_rejects_non_hub(tmp_path: Path) -> None:
    context = _setup_hub_aggregator_context(tmp_path)
    result = dispatch(
        "place_aggregated_order",
        {
            "order_id": "#AGG-1",
            "committing_owner_id": "frank",
            "spoke_request_ids": ["REQ-1"],
            "payment_method_id": "PM-10",
            "shipping_address_id": "ADDR-10",
        },
        context,
    )
    assert result["ok"] is False
    assert result["error"] == "committer_is_not_hub"


def test_place_aggregated_order_hub_commits_successfully(tmp_path: Path) -> None:
    context = _setup_hub_aggregator_context(tmp_path)
    result = dispatch(
        "place_aggregated_order",
        {
            "order_id": "#AGG-1",
            "committing_owner_id": "eve",
            "spoke_request_ids": ["REQ-frank-1", "REQ-grace-1"],
            "payment_method_id": "PM-10",
            "shipping_address_id": "ADDR-10",
        },
        context,
    )
    assert result["ok"] is True
    assert result["order_id"] == "#AGG-1"
    assert result["line_item_count"] == 2


# ---------------------------------------------------------------------------
# Tests for submit_purchase_request
# ---------------------------------------------------------------------------

def test_submit_purchase_request_rejects_non_spoke(tmp_path: Path) -> None:
    context = _setup_hub_aggregator_context(tmp_path)
    result = dispatch(
        "submit_purchase_request",
        {
            "item_id": "ITEM-99",
            "qty": 1,
            "target_price": 50.0,
            "preferred_options": {},
            "delivery_address_id": "ADDR-11",
            "submitting_owner_id": "eve",
        },
        context,
    )
    assert result["ok"] is False
    assert result["error"] == "submitter_not_a_spoke"


def test_submit_purchase_request_succeeds_for_spoke(tmp_path: Path) -> None:
    context = _setup_hub_aggregator_context(tmp_path)
    result = dispatch(
        "submit_purchase_request",
        {
            "item_id": "ITEM-99",
            "qty": 2,
            "target_price": 49.99,
            "preferred_options": {"color": "blue"},
            "delivery_address_id": "ADDR-11",
            "submitting_owner_id": "frank",
        },
        context,
    )
    assert result["ok"] is True
    assert result["item_id"] == "ITEM-99"
    assert result["submitting_owner_id"] == "frank"


# ---------------------------------------------------------------------------
# Tests for request_return
# ---------------------------------------------------------------------------

def test_request_return_cross_account_rejects_non_recipient(tmp_path: Path) -> None:
    context = _setup_cross_account_context(tmp_path)
    _seed_gift_order(context, order_id="#W-RET-10")
    result = dispatch(
        "request_return",
        {
            "order_id": "#W-RET-10",
            "items": ["ITEM-A"],
            "requesting_owner_id": "carol",
        },
        context,
    )
    assert result["ok"] is False
    assert result["error"] == "requester_not_recipient"


def test_request_return_cross_account_succeeds_for_recipient(tmp_path: Path) -> None:
    context = _setup_cross_account_context(tmp_path)
    _seed_gift_order(context, order_id="#W-RET-10")
    result = dispatch(
        "request_return",
        {
            "order_id": "#W-RET-10",
            "items": ["ITEM-A"],
            "requesting_owner_id": "dave",
        },
        context,
    )
    assert result["ok"] is True
    assert result["order_id"] == "#W-RET-10"
    assert result["items"] == ["ITEM-A"]


def test_request_return_store_rep_dyad_rejects_non_customer(tmp_path: Path) -> None:
    context = _setup_store_rep_dyad_context(tmp_path)
    _seed_retail_order(context, order_id="#W-STORE-1", owner_id="iris")
    result = dispatch(
        "request_return",
        {
            "order_id": "#W-STORE-1",
            "items": ["ITEM-B"],
            "requesting_owner_id": "iris",
        },
        context,
    )
    assert result["ok"] is False
    assert result["error"] == "requester_not_customer"


def test_request_return_store_rep_dyad_succeeds_for_customer(tmp_path: Path) -> None:
    context = _setup_store_rep_dyad_context(tmp_path)
    _seed_retail_order(context, order_id="#W-STORE-1", owner_id="iris")
    result = dispatch(
        "request_return",
        {
            "order_id": "#W-STORE-1",
            "items": ["ITEM-B"],
            "requesting_owner_id": "hank",
        },
        context,
    )
    assert result["ok"] is True
    assert result["order_id"] == "#W-STORE-1"
