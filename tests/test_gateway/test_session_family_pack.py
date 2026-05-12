"""Integration test: Session.build wires tau2_retail handlers automatically.

Validates the Phase 3 follow-up integration point. When a session is
built with ``family_id='tau2_retail'`` and a ``resource_root`` that
points at a materialized bundle's ``resources/``, the tau2 retail tool
handlers are registered against the session's McpHost without any
extra setup. This is what unblocks the live Docker batch path:
``naturalize_and_run_batch`` (or any caller that drives ``Session.build``)
just passes ``family_id`` and the handlers come for free.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.gateway.session import Session
from clawsocialarena.generator.family_packs.tau2_retail import (
    load_household_exchange_scenario,
    materialize_household_bundle,
)
from clawsocialarena.mcp_tools.tau2_retail import TOOL_NAMES
from clawsocialarena.types import AuditCondition


@pytest.fixture
def materialized_bundle_dir(tmp_path: Path) -> Path:
    bundle = load_household_exchange_scenario()
    return materialize_household_bundle(bundle, tmp_path / "scenario")


def test_session_build_baseline_registers_family_pack_handlers(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    """Under BASELINE, the session has no audit substrate but still
    registers MCP handlers so the agents can call the tools."""
    session = Session.build(
        scenario_id="tau2_retail_smoke",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",  # baseline ignores db_path
        resource_root=materialized_bundle_dir / "resources",
        family_id="tau2_retail",
    )
    registered = set(session.mcp_host.tools())
    assert set(TOOL_NAMES).issubset(registered)


def test_session_build_passive_registers_family_pack_handlers(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    """Under PASSIVE, the audit substrate is wired AND the family-pack
    handlers are registered. This is the production smoke path."""
    db_path = tmp_path / "action_log.db"
    session = Session.build(
        scenario_id="tau2_retail_smoke",
        condition=AuditCondition.PASSIVE,
        db_path=db_path,
        resource_root=materialized_bundle_dir / "resources",
        work_dir=tmp_path,
        family_id="tau2_retail",
    )
    registered = set(session.mcp_host.tools())
    assert set(TOOL_NAMES).issubset(registered)
    assert session.action_log is not None
    assert session.shadow_log is not None


def test_session_build_without_family_id_skips_family_pack(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    """Legacy bundles that omit family_id keep the old behavior: no
    family-pack handlers registered."""
    session = Session.build(
        scenario_id="legacy_no_family",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",
        resource_root=materialized_bundle_dir / "resources",
    )
    registered = set(session.mcp_host.tools())
    assert not (set(TOOL_NAMES) & registered)


def test_session_build_unknown_family_id_skips_silently(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    """Unknown family_id is treated as a no-op so a forward-compatible
    bundle (declaring a family pack the runtime does not know about
    yet) does not crash construction. A future strict mode could
    promote this to an error."""
    session = Session.build(
        scenario_id="future_family",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",
        resource_root=materialized_bundle_dir / "resources",
        family_id="marble_research_v99",
    )
    registered = set(session.mcp_host.tools())
    assert not (set(TOOL_NAMES) & registered)


def test_session_build_custom_household_context(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    """family_pack_context overrides the household defaults."""
    session = Session.build(
        scenario_id="custom_household",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",
        resource_root=materialized_bundle_dir / "resources",
        family_id="tau2_retail",
        family_pack_context={
            "household_id": "HH-99",
            "primary_owner_id": "carol",
            "secondary_owner_ids": ["dave", "erin"],
        },
    )
    # The handlers are bound to the custom context; we cannot easily
    # inspect closure state but a smoke call should reflect the
    # override.
    import asyncio
    result = asyncio.run(
        session.mcp_host.dispatch(
            "find_user_id_by_name_zip",
            {"first_name": "carol", "zip": "00000"},
        )
    )
    assert result["ok"] is True
    assert result["user_id"] == "carol"
    assert result["household_id"] == "HH-99"


@pytest.mark.asyncio
async def test_session_built_handlers_dispatch_against_real_sqlite(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    """End-to-end: the session-built handlers read from the materialized
    bundle's SQLite databases without any extra wiring."""
    session = Session.build(
        scenario_id="dispatch_smoke",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "action_log.db",
        resource_root=materialized_bundle_dir / "resources",
        work_dir=tmp_path,
        family_id="tau2_retail",
    )

    auth = await session.mcp_host.dispatch(
        "find_user_id_by_name_zip",
        {"first_name": "alice", "zip": "19122"},
    )
    assert auth["ok"]

    import sqlite3

    conn = sqlite3.connect(
        materialized_bundle_dir / "resources/users/alice/db/personal.sqlite"
    )
    try:
        any_order_id = conn.execute("SELECT order_id FROM orders LIMIT 1").fetchone()[0]
    finally:
        conn.close()

    details = await session.mcp_host.dispatch(
        "get_order_details",
        {"order_id": any_order_id, "caller_id": "alice"},
    )
    assert details["ok"]
    assert details["order"]["household_id"] == "HH-7"
