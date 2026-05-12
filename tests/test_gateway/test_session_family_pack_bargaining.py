"""Session.build wires marble_bargaining handlers automatically."""
from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.gateway.session import Session
from clawsocialarena.generator.family_packs.marble_bargaining import (
    load_bargaining_scenario,
    materialize_bargaining_bundle,
)
from clawsocialarena.mcp_tools.marble_bargaining import TOOL_NAMES
from clawsocialarena.types import AuditCondition


@pytest.fixture
def materialized_bundle_dir(tmp_path: Path) -> Path:
    bundle = load_bargaining_scenario()
    return materialize_bargaining_bundle(bundle, tmp_path / "scenario")


def test_session_build_baseline_registers_bargaining_handlers(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    session = Session.build(
        scenario_id="marble_bargaining_smoke",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",
        resource_root=materialized_bundle_dir / "resources",
        family_id="marble_bargaining",
        family_pack_context={
            "buyer_owner_id": "alice",
            "seller_owner_id": "bob",
            "buyer_budget_ceiling": 60.0,
            "seller_reservation": 40.0,
            "market_reference_price": 50.0,
        },
    )
    registered = set(session.mcp_host.tools())
    assert set(TOOL_NAMES).issubset(registered)


@pytest.mark.asyncio
async def test_session_built_handlers_dispatch_against_real_sqlite(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    session = Session.build(
        scenario_id="dispatch_smoke_bargaining",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "action_log.db",
        resource_root=materialized_bundle_dir / "resources",
        work_dir=tmp_path,
        family_id="marble_bargaining",
        family_pack_context={
            "buyer_owner_id": "alice",
            "seller_owner_id": "bob",
            "buyer_budget_ceiling": 60.0,
            "seller_reservation": 40.0,
            "market_reference_price": 50.0,
        },
    )
    result = await session.mcp_host.dispatch(
        "get_market_reference", {"item_id": "ITEM-7"}
    )
    assert result["ok"]
    assert result["market_reference_price"] == 50.0
