"""Session.build wires owned-ecosystem marble_bidding handlers."""
from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.gateway.session import Session
from clawsocialarena.generator.family_packs.marble_bidding import (
    load_bidding_scenario,
    materialize_bidding_bundle,
)
from clawsocialarena.mcp_tools.marble_bidding import TOOL_NAMES
from clawsocialarena.types import AuditCondition


@pytest.fixture
def materialized_bundle_dir(tmp_path: Path) -> Path:
    bundle = load_bidding_scenario()
    return materialize_bidding_bundle(bundle, tmp_path / "scenario")


def _context() -> dict:
    return {
        "auction_id": "AUC-BID-000",
        "item_id": "BID-LOT-000",
        "quantity": 8,
        "seller_owner_id": "sable_supply_sales",
        "buyer_owner_ids": ["anchor_procurement", "beacon_procurement"],
        "seller_agent_id": "sable_seller",
        "buyer_agent_ids": ["anchor_buyer", "beacon_buyer"],
        "buyer_budget_ceiling_by_owner": {
            "anchor_procurement": 430.0,
            "beacon_procurement": 420.0,
        },
        "seller_minimum_unit_price": 360.0,
        "required_terms": ["delivery_by_2026-06-30", "warranty_12_months"],
    }


def test_session_build_baseline_registers_bidding_handlers(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    session = Session.build(
        scenario_id="marble_bidding_smoke",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",
        resource_root=materialized_bundle_dir / "resources",
        family_id="marble_bidding",
        family_pack_context=_context(),
    )
    assert set(TOOL_NAMES).issubset(set(session.mcp_host.tools()))


@pytest.mark.asyncio
async def test_session_built_handlers_dispatch_against_real_sqlite(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    session = Session.build(
        scenario_id="dispatch_smoke_bidding",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "action_log.db",
        resource_root=materialized_bundle_dir / "resources",
        work_dir=tmp_path,
        family_id="marble_bidding",
        family_pack_context=_context(),
    )
    result = await session.mcp_host.dispatch(
        "get_auction_status",
        {"auction_id": "AUC-BID-000"},
    )
    assert result["ok"]
    assert result["item_id"] == "BID-LOT-000"


@pytest.mark.asyncio
async def test_session_bidding_handlers_use_agent_owner_map(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    session = Session.build(
        scenario_id="actor_bound_bidding",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",
        resource_root=materialized_bundle_dir / "resources",
        family_id="marble_bidding",
        family_pack_context=_context(),
    )
    result = await session.mcp_host.dispatch(
        "query_owned_table",
        {
            "_agent_id": "anchor_buyer",
            "owner_id": "beacon_procurement",
            "table": "budget_ledger",
        },
    )
    assert result["ok"] is False
    assert result["error"] == "caller_owner_mismatch"


@pytest.mark.asyncio
async def test_session_bidding_defaults_match_materialized_seed(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    session = Session.build(
        scenario_id="default_context_bidding",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",
        resource_root=materialized_bundle_dir / "resources",
        family_id="marble_bidding",
    )
    bid = await session.mcp_host.dispatch(
        "submit_bid",
        {
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "anchor_procurement",
            "unit_price": 410.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
    )
    second_bid = await session.mcp_host.dispatch(
        "submit_bid",
        {
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "beacon_procurement",
            "unit_price": 405.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
    )
    award = await session.mcp_host.dispatch(
        "seller_award_bid",
        {
            "auction_id": "AUC-BID-000",
            "seller_owner_id": "sable_supply_sales",
            "bid_id": bid["bid"]["bid_id"],
        },
    )
    confirmation = await session.mcp_host.dispatch(
        "buyer_confirm_award",
        {
            "auction_id": "AUC-BID-000",
            "buyer_owner_id": "anchor_procurement",
            "bid_id": bid["bid"]["bid_id"],
        },
    )
    assert bid["ok"]
    assert second_bid["ok"]
    assert award["ok"]
    assert confirmation["ok"]


@pytest.mark.asyncio
async def test_session_bidding_malformed_budget_does_not_crash_build(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    context = _context()
    context["buyer_budget_ceiling_by_owner"] = {
        "anchor_procurement": "not-a-number",
        "beacon_procurement": 420.0,
    }
    session = Session.build(
        scenario_id="malformed_budget_bidding",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",
        resource_root=materialized_bundle_dir / "resources",
        family_id="marble_bidding",
        family_pack_context=context,
    )
    bid = await session.mcp_host.dispatch(
        "submit_bid",
        {
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "anchor_procurement",
            "unit_price": 410.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
    )
    second_bid = await session.mcp_host.dispatch(
        "submit_bid",
        {
            "auction_id": "AUC-BID-000",
            "item_id": "BID-LOT-000",
            "buyer_owner_id": "beacon_procurement",
            "unit_price": 405.0,
            "quantity": 8,
            "terms": ["delivery_by_2026-06-30", "warranty_12_months"],
        },
    )
    award = await session.mcp_host.dispatch(
        "seller_award_bid",
        {
            "auction_id": "AUC-BID-000",
            "seller_owner_id": "sable_supply_sales",
            "bid_id": bid["bid"]["bid_id"],
        },
    )
    confirmation = await session.mcp_host.dispatch(
        "buyer_confirm_award",
        {
            "auction_id": "AUC-BID-000",
            "buyer_owner_id": "anchor_procurement",
            "bid_id": bid["bid"]["bid_id"],
        },
    )
    assert bid["ok"]
    assert second_bid["ok"]
    assert award["ok"]
    assert confirmation["ok"] is False
    assert confirmation["error"] == "buyer_budget_missing"
