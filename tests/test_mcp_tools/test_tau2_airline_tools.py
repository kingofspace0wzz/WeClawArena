"""Tests for tau2_airline MCP tool handlers.

Validates each handler against a materialized bundle's per-passenger
SQLite databases, enforces the consent rules, and confirms returned
dicts the evaluation pipeline can read.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.gateway.mcp_host import McpHost
from clawsocialarena.generator.family_packs.tau2_airline import (
    load_group_seat_change_scenario,
    materialize_group_booking_bundle,
)
from clawsocialarena.mcp_tools.tau2_airline import (
    GroupBookingContext,
    TOOL_NAMES,
    dispatch,
    register_tau2_airline_handlers,
)


@pytest.fixture
def group_context(tmp_path: Path) -> GroupBookingContext:
    bundle = load_group_seat_change_scenario()
    bundle_dir = tmp_path / "scenario"
    materialize_group_booking_bundle(bundle, bundle_dir)
    return GroupBookingContext(
        resources_root=bundle_dir / "resources",
        group_id="GRP-7",
        organizer_owner_id="alice",
        traveler_owner_ids=("bob",),
    )


def _reservation_id(group_context: GroupBookingContext) -> str:
    import sqlite3

    db_path = (
        group_context.resources_root / "passengers" / "alice" / "db" / "personal.sqlite"
    )
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT reservation_id FROM reservations LIMIT 1").fetchone()
    return row[0]


def test_find_user_id_resolves_group_member(
    group_context: GroupBookingContext,
) -> None:
    result = dispatch("find_user_id_by_name", {"first_name": "alice"}, group_context)
    assert result["ok"] is True
    assert result["user_id"] == "alice"


def test_find_user_id_rejects_outsider(
    group_context: GroupBookingContext,
) -> None:
    result = dispatch("find_user_id_by_name", {"first_name": "mallory"}, group_context)
    assert result["ok"] is False
    assert result["error"] == "user_not_found"


def test_get_user_details_labels_roles(
    group_context: GroupBookingContext,
) -> None:
    organizer = dispatch("get_user_details", {"user_id": "alice"}, group_context)
    traveler = dispatch("get_user_details", {"user_id": "bob"}, group_context)
    assert organizer["role"] == "group_organizer"
    assert traveler["role"] == "group_traveler"


def test_commit_blocked_without_consent(
    group_context: GroupBookingContext,
) -> None:
    rid = _reservation_id(group_context)
    request = dispatch(
        "request_seat_change",
        {
            "reservation_id": rid,
            "passenger_id": "bob",
            "new_seat": "1A",
            "requester_id": "alice",
        },
        group_context,
    )
    assert request["ok"]
    commit = dispatch(
        "commit_seat_change",
        {"reservation_id": rid, "committer_id": "alice"},
        group_context,
    )
    assert commit["ok"] is False
    assert commit["error"] == "consent_missing"
    assert commit["passenger_id"] == "bob"


def test_commit_succeeds_after_passenger_consents(
    group_context: GroupBookingContext,
) -> None:
    rid = _reservation_id(group_context)
    dispatch(
        "request_seat_change",
        {
            "reservation_id": rid,
            "passenger_id": "bob",
            "new_seat": "1A",
            "requester_id": "alice",
        },
        group_context,
    )
    consent = dispatch(
        "consent_to_seat_change",
        {"reservation_id": rid, "consenter_id": "bob"},
        group_context,
    )
    assert consent["ok"]
    commit = dispatch(
        "commit_seat_change",
        {"reservation_id": rid, "committer_id": "alice"},
        group_context,
    )
    assert commit["ok"]
    assert commit["status"] == "finalized"
    assert commit["committed_change"]["passenger_id"] == "bob"


def test_organizer_cannot_forge_consent_for_traveler(
    group_context: GroupBookingContext,
) -> None:
    rid = _reservation_id(group_context)
    dispatch(
        "request_seat_change",
        {
            "reservation_id": rid,
            "passenger_id": "bob",
            "new_seat": "1A",
            "requester_id": "alice",
        },
        group_context,
    )
    # Alice tries to consent on Bob's behalf -- denied.
    forged = dispatch(
        "consent_to_seat_change",
        {"reservation_id": rid, "consenter_id": "alice"},
        group_context,
    )
    assert forged["ok"] is False
    assert forged["error"] == "consent_for_other_passenger_denied"


def test_only_organizer_can_commit(
    group_context: GroupBookingContext,
) -> None:
    rid = _reservation_id(group_context)
    dispatch(
        "request_seat_change",
        {
            "reservation_id": rid,
            "passenger_id": "bob",
            "new_seat": "1A",
            "requester_id": "alice",
        },
        group_context,
    )
    dispatch(
        "consent_to_seat_change",
        {"reservation_id": rid, "consenter_id": "bob"},
        group_context,
    )
    denied = dispatch(
        "commit_seat_change",
        {"reservation_id": rid, "committer_id": "bob"},
        group_context,
    )
    assert denied["ok"] is False
    assert denied["error"] == "authorization_denied"


def test_register_tau2_airline_handlers_wires_all_tools(
    group_context: GroupBookingContext,
) -> None:
    host = McpHost()
    register_tau2_airline_handlers(host, context=group_context)
    registered = set(host.tools())
    assert set(TOOL_NAMES).issubset(registered)


@pytest.mark.asyncio
async def test_dispatch_through_mcp_host(
    group_context: GroupBookingContext,
) -> None:
    host = McpHost()
    register_tau2_airline_handlers(host, context=group_context)
    result = await host.dispatch("find_user_id_by_name", {"first_name": "alice"})
    assert result["ok"] is True
    assert result["user_id"] == "alice"
