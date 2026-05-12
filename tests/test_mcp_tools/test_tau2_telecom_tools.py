"""Tests for tau2_telecom MCP tool handlers."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.gateway.mcp_host import McpHost
from clawsocialarena.generator.family_packs.tau2_telecom import (
    load_family_plan_roaming_scenario,
    materialize_family_plan_bundle,
)
from clawsocialarena.mcp_tools.tau2_telecom import (
    FamilyPlanContext,
    TOOL_NAMES,
    dispatch,
    register_tau2_telecom_handlers,
)


@pytest.fixture
def plan_context(tmp_path: Path) -> FamilyPlanContext:
    bundle = load_family_plan_roaming_scenario()
    bundle_dir = tmp_path / "scenario"
    materialize_family_plan_bundle(bundle, bundle_dir)
    return FamilyPlanContext(
        resources_root=bundle_dir / "resources",
        account_id="ACC-7",
        primary_owner_id="alice",
        secondary_owner_ids=("bob",),
    )


def _line_id_for(plan_context: FamilyPlanContext, owner: str) -> str:
    db_path = plan_context.resources_root / "users" / "alice" / "db" / "personal.sqlite"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT line_id FROM lines WHERE owner_id = ?", (owner,)
        ).fetchone()
    return row[0]


def test_find_user_id_resolves_account_member(
    plan_context: FamilyPlanContext,
) -> None:
    result = dispatch(
        "find_user_id_by_name", {"first_name": "alice"}, plan_context
    )
    assert result["ok"]
    assert result["user_id"] == "alice"
    assert result["account_id"] == "ACC-7"


def test_find_user_id_rejects_outsider(
    plan_context: FamilyPlanContext,
) -> None:
    result = dispatch(
        "find_user_id_by_name", {"first_name": "mallory"}, plan_context
    )
    assert result["ok"] is False


def test_get_user_details_labels_roles(
    plan_context: FamilyPlanContext,
) -> None:
    primary = dispatch("get_user_details", {"user_id": "alice"}, plan_context)
    secondary = dispatch("get_user_details", {"user_id": "bob"}, plan_context)
    assert primary["role"] == "primary_account_holder"
    assert secondary["role"] == "secondary_line_owner"


def test_secondary_cannot_see_primary_line(
    plan_context: FamilyPlanContext,
) -> None:
    primary_line = _line_id_for(plan_context, "alice")
    result = dispatch(
        "get_line_details",
        {"line_id": primary_line, "caller_id": "bob"},
        plan_context,
    )
    assert result["ok"] is False
    assert result["error"] == "line_not_visible_to_caller"


def test_secondary_can_see_own_line(
    plan_context: FamilyPlanContext,
) -> None:
    secondary_line = _line_id_for(plan_context, "bob")
    result = dispatch(
        "get_line_details",
        {"line_id": secondary_line, "caller_id": "bob"},
        plan_context,
    )
    assert result["ok"]
    assert result["line"]["owner_id"] == "bob"


def test_commit_blocked_without_consent(
    plan_context: FamilyPlanContext,
) -> None:
    secondary_line = _line_id_for(plan_context, "bob")
    dispatch(
        "request_line_change",
        {
            "line_id": secondary_line,
            "requester_id": "bob",
            "change_kind": "toggle_roaming",
            "new_value": True,
        },
        plan_context,
    )
    commit = dispatch(
        "commit_line_change",
        {"line_id": secondary_line, "committer_id": "alice"},
        plan_context,
    )
    assert commit["ok"] is False
    assert commit["error"] == "consent_missing"
    assert commit["line_owner_id"] == "bob"


def test_commit_succeeds_after_consent_and_flips_roaming(
    plan_context: FamilyPlanContext,
) -> None:
    secondary_line = _line_id_for(plan_context, "bob")
    dispatch(
        "request_line_change",
        {
            "line_id": secondary_line,
            "requester_id": "bob",
            "change_kind": "toggle_roaming",
            "new_value": True,
        },
        plan_context,
    )
    consent = dispatch(
        "consent_to_line_change",
        {"line_id": secondary_line, "consenter_id": "bob"},
        plan_context,
    )
    assert consent["ok"]
    commit = dispatch(
        "commit_line_change",
        {"line_id": secondary_line, "committer_id": "alice"},
        plan_context,
    )
    assert commit["ok"]
    assert commit["status"] == "finalized"
    # Roaming should now be flipped to enabled in both DBs.
    for owner in ("alice", "bob"):
        db_path = plan_context.resources_root / "users" / owner / "db" / "personal.sqlite"
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT roaming_enabled FROM lines WHERE line_id = ?",
                (secondary_line,),
            ).fetchone()
            assert row[0] == 1, f"roaming not flipped in {owner}'s db"


def test_primary_cannot_consent_for_secondary_line(
    plan_context: FamilyPlanContext,
) -> None:
    secondary_line = _line_id_for(plan_context, "bob")
    dispatch(
        "request_line_change",
        {
            "line_id": secondary_line,
            "requester_id": "alice",
            "change_kind": "toggle_roaming",
            "new_value": True,
        },
        plan_context,
    )
    forged = dispatch(
        "consent_to_line_change",
        {"line_id": secondary_line, "consenter_id": "alice"},
        plan_context,
    )
    assert forged["ok"] is False
    assert forged["error"] == "consent_for_other_line_denied"


def test_only_primary_can_commit(
    plan_context: FamilyPlanContext,
) -> None:
    secondary_line = _line_id_for(plan_context, "bob")
    dispatch(
        "request_line_change",
        {
            "line_id": secondary_line,
            "requester_id": "bob",
            "change_kind": "toggle_roaming",
            "new_value": True,
        },
        plan_context,
    )
    dispatch(
        "consent_to_line_change",
        {"line_id": secondary_line, "consenter_id": "bob"},
        plan_context,
    )
    denied = dispatch(
        "commit_line_change",
        {"line_id": secondary_line, "committer_id": "bob"},
        plan_context,
    )
    assert denied["ok"] is False
    assert denied["error"] == "authorization_denied"


def test_only_primary_can_dispute_charge(
    plan_context: FamilyPlanContext,
) -> None:
    denied = dispatch(
        "dispute_charge",
        {"bill_id": "B1001", "requester_id": "bob"},
        plan_context,
    )
    assert denied["ok"] is False
    assert denied["error"] == "authorization_denied"
    allowed = dispatch(
        "dispute_charge",
        {"bill_id": "B1001", "requester_id": "alice"},
        plan_context,
    )
    assert allowed["ok"]
    assert allowed["status"] == "disputed"


def test_register_telecom_handlers_wires_all_tools(
    plan_context: FamilyPlanContext,
) -> None:
    host = McpHost()
    register_tau2_telecom_handlers(host, context=plan_context)
    registered = set(host.tools())
    assert set(TOOL_NAMES).issubset(registered)


@pytest.mark.asyncio
async def test_dispatch_through_mcp_host(
    plan_context: FamilyPlanContext,
) -> None:
    host = McpHost()
    register_tau2_telecom_handlers(host, context=plan_context)
    result = await host.dispatch(
        "find_user_id_by_name", {"first_name": "alice"}
    )
    assert result["ok"]
    assert result["user_id"] == "alice"
