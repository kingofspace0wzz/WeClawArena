"""Session.build wires wildclaw_social handlers automatically."""
from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.gateway.session import Session
from clawsocialarena.generator.family_packs.wildclaw_social import (
    load_meeting_negotiation_scenario,
    materialize_meeting_negotiation_bundle,
)
from clawsocialarena.mcp_tools.wildclaw_social import TOOL_NAMES
from clawsocialarena.types import AuditCondition


@pytest.fixture
def materialized_bundle_dir(tmp_path: Path) -> Path:
    bundle = load_meeting_negotiation_scenario()
    return materialize_meeting_negotiation_bundle(bundle, tmp_path / "scenario")


def test_session_build_baseline_registers_social_handlers(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    session = Session.build(
        scenario_id="wildclaw_social_smoke",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",
        resource_root=materialized_bundle_dir / "resources",
        family_id="wildclaw_social",
        family_pack_context={
            "organizer_owner_id": "alice",
            "participant_owner_ids": ["bob", "carol", "dave"],
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
        scenario_id="dispatch_smoke_social",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "action_log.db",
        resource_root=materialized_bundle_dir / "resources",
        work_dir=tmp_path,
        family_id="wildclaw_social",
        family_pack_context={
            "organizer_owner_id": "alice",
            "participant_owner_ids": ["bob", "carol", "dave"],
        },
    )
    result = await session.mcp_host.dispatch(
        "check_availability", {"owner_id": "bob", "caller_id": "bob"}
    )
    assert result["ok"]
    assert result["slots"]
