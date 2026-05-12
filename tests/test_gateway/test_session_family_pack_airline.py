"""Session.build wires tau2_airline handlers automatically.

Parallels the tau2_retail equivalent: confirms that passing
``family_id='tau2_airline'`` with a materialized airline bundle is
enough for the gateway to register all seven tau2_airline tool
handlers without any extra wiring on the caller side.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.gateway.session import Session
from clawsocialarena.generator.family_packs.tau2_airline import (
    load_group_seat_change_scenario,
    materialize_group_booking_bundle,
)
from clawsocialarena.mcp_tools.tau2_airline import TOOL_NAMES
from clawsocialarena.types import AuditCondition


@pytest.fixture
def materialized_bundle_dir(tmp_path: Path) -> Path:
    bundle = load_group_seat_change_scenario()
    return materialize_group_booking_bundle(bundle, tmp_path / "scenario")


def test_session_build_baseline_registers_airline_handlers(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    session = Session.build(
        scenario_id="tau2_airline_smoke",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",
        resource_root=materialized_bundle_dir / "resources",
        family_id="tau2_airline",
    )
    registered = set(session.mcp_host.tools())
    assert set(TOOL_NAMES).issubset(registered)


def test_session_build_passive_registers_airline_handlers(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    session = Session.build(
        scenario_id="tau2_airline_smoke_passive",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "action_log.db",
        resource_root=materialized_bundle_dir / "resources",
        work_dir=tmp_path,
        family_id="tau2_airline",
    )
    registered = set(session.mcp_host.tools())
    assert set(TOOL_NAMES).issubset(registered)
    assert session.action_log is not None
    assert session.shadow_log is not None


@pytest.mark.asyncio
async def test_session_built_handlers_dispatch_against_real_sqlite(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    session = Session.build(
        scenario_id="dispatch_smoke_airline",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "action_log.db",
        resource_root=materialized_bundle_dir / "resources",
        work_dir=tmp_path,
        family_id="tau2_airline",
    )
    result = await session.mcp_host.dispatch(
        "find_user_id_by_name", {"first_name": "alice"}
    )
    assert result["ok"]
    assert result["user_id"] == "alice"
    assert result["group_id"] == "GRP-7"
