"""Session.build wires marble_research handlers automatically."""
from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.gateway.session import Session
from clawsocialarena.generator.family_packs.marble_research import (
    load_research_collaboration_scenario,
    materialize_research_collaboration_bundle,
)
from clawsocialarena.mcp_tools.marble_research import TOOL_NAMES
from clawsocialarena.types import AuditCondition


@pytest.fixture
def materialized_bundle_dir(tmp_path: Path) -> Path:
    bundle = load_research_collaboration_scenario()
    return materialize_research_collaboration_bundle(bundle, tmp_path / "scenario")


def test_session_build_baseline_registers_research_handlers(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    session = Session.build(
        scenario_id="marble_research_smoke",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",
        resource_root=materialized_bundle_dir / "resources",
        family_id="marble_research",
        family_pack_context={
            "convener_owner_id": "alice",
            "peer_owner_ids": ["bob", "carol"],
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
        scenario_id="dispatch_smoke_research",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "action_log.db",
        resource_root=materialized_bundle_dir / "resources",
        work_dir=tmp_path,
        family_id="marble_research",
        family_pack_context={
            "convener_owner_id": "alice",
            "peer_owner_ids": ["bob", "carol"],
        },
    )
    result = await session.mcp_host.dispatch("get_pi_details", {"pi_id": "alice"})
    assert result["ok"]
    assert result["role"] == "convener_pi"
