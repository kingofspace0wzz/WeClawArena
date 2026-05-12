"""Session.build wires tau2_telecom handlers automatically."""
from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.gateway.session import Session
from clawsocialarena.generator.family_packs.tau2_telecom import (
    load_family_plan_roaming_scenario,
    materialize_family_plan_bundle,
)
from clawsocialarena.mcp_tools.tau2_telecom import TOOL_NAMES
from clawsocialarena.types import AuditCondition


@pytest.fixture
def materialized_bundle_dir(tmp_path: Path) -> Path:
    bundle = load_family_plan_roaming_scenario()
    return materialize_family_plan_bundle(bundle, tmp_path / "scenario")


def test_session_build_baseline_registers_telecom_handlers(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    session = Session.build(
        scenario_id="tau2_telecom_smoke",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",
        resource_root=materialized_bundle_dir / "resources",
        family_id="tau2_telecom",
    )
    registered = set(session.mcp_host.tools())
    assert set(TOOL_NAMES).issubset(registered)


def test_session_build_passive_registers_telecom_handlers(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    session = Session.build(
        scenario_id="tau2_telecom_smoke_passive",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "action_log.db",
        resource_root=materialized_bundle_dir / "resources",
        work_dir=tmp_path,
        family_id="tau2_telecom",
    )
    registered = set(session.mcp_host.tools())
    assert set(TOOL_NAMES).issubset(registered)


@pytest.mark.asyncio
async def test_session_built_handlers_dispatch_against_real_sqlite(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    session = Session.build(
        scenario_id="dispatch_smoke_telecom",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "action_log.db",
        resource_root=materialized_bundle_dir / "resources",
        work_dir=tmp_path,
        family_id="tau2_telecom",
    )
    result = await session.mcp_host.dispatch(
        "find_user_id_by_name", {"first_name": "alice"}
    )
    assert result["ok"]
    assert result["user_id"] == "alice"
    assert result["account_id"] == "ACC-7"
