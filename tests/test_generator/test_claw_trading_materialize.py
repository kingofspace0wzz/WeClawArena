"""Tests for the claw_trading materializer."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.generator.family_packs.claw_trading.loader import (
    load_trading_club_scenario,
)
from clawsocialarena.generator.family_packs.claw_trading.materialize import (
    materialize_trading_bundle,
)


@pytest.fixture
def simple_bundle_dir(tmp_path: Path) -> Path:
    bundle = load_trading_club_scenario()
    return materialize_trading_bundle(bundle, tmp_path / "simple")


@pytest.fixture
def multi_team_bundle_dir(tmp_path: Path) -> Path:
    bundle = load_trading_club_scenario(
        case_key="multi_team_debate_005",
        scenario_id="claw_trading_multi_team_005",
    )
    return materialize_trading_bundle(bundle, tmp_path / "multi_team")


def test_writes_top_level_artifacts(simple_bundle_dir: Path) -> None:
    for name in (
        "scenario.json",
        "scenario.gt.json",
        "family_pack_context.json",
        "docker-compose.yml",
    ):
        assert (simple_bundle_dir / name).is_file()


def test_personas_dir_has_agent_files(simple_bundle_dir: Path) -> None:
    personas = simple_bundle_dir / "personas"
    assert personas.is_dir()
    system_files = list(personas.glob("*.system.md"))
    tools_files = list(personas.glob("*.tools.json"))
    assert len(system_files) >= 3
    assert len(tools_files) >= 3


def test_mcp_dir_has_tool_stubs(simple_bundle_dir: Path) -> None:
    mcp = simple_bundle_dir / "mcp"
    assert mcp.is_dir()
    stubs = list(mcp.glob("*.json"))
    assert len(stubs) >= 12  # Base tools
    # Check a stub has correct structure
    stub = json.loads(stubs[0].read_text())
    assert "tool_name" in stub
    assert "audit_class" in stub


def test_sqlite_has_members_and_proposals(simple_bundle_dir: Path) -> None:
    db_path = simple_bundle_dir / "resources" / "shared" / "CLUB-ALPHA" / "club.sqlite"
    assert db_path.is_file()
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"members", "proposals", "votes"}.issubset(tables)
        member_count = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
        assert member_count >= 3


def test_per_member_portfolio_resources(simple_bundle_dir: Path) -> None:
    agents_dir = simple_bundle_dir / "resources" / "agents"
    assert agents_dir.is_dir()
    # Check scenario members (alice, bob, carol) have holdings
    scenario_members = ["alice", "bob", "carol"]
    for mid in scenario_members:
        holdings_path = agents_dir / mid / "files" / "holdings.json"
        assert holdings_path.is_file(), f"Missing holdings for {mid}"
        holdings = json.loads(holdings_path.read_text())
        assert "access_restricted_to" in holdings


def test_market_snapshot_exists(simple_bundle_dir: Path) -> None:
    snapshot = simple_bundle_dir / "resources" / "shared" / "market" / "snapshot.json"
    assert snapshot.is_file()
    data = json.loads(snapshot.read_text())
    assert "context" in data
    assert "data" in data


def test_gt_json_has_topology_aware_invariants(simple_bundle_dir: Path) -> None:
    gt = json.loads((simple_bundle_dir / "scenario.gt.json").read_text())
    inv = gt["invariants"]
    assert "privacy_must_not_cross" in inv
    assert "security_must_not_happen" in inv
    assert "governance_must_not_happen" in inv
    # Simple topology: forbidden role is club_member
    assert inv["security_must_not_happen"][0]["forbidden_agent_roles"] == ["club_member"]


def test_gt_json_mcp_manifest_includes_multi_team_tools(
    simple_bundle_dir: Path,
) -> None:
    gt = json.loads((simple_bundle_dir / "scenario.gt.json").read_text())
    manifest = gt["mcp_tool_manifest"]
    assert "read_analyst_notes" in manifest
    assert "debate_thesis" in manifest
    assert len(manifest) == 17


def test_multi_team_writes_analyst_notes(multi_team_bundle_dir: Path) -> None:
    agents_dir = multi_team_bundle_dir / "resources" / "agents"
    assert agents_dir.is_dir()
    members_with_notes = [
        d for d in agents_dir.iterdir()
        if (d / "files" / "analyst_notes.json").is_file()
    ]
    assert len(members_with_notes) >= 3


def test_multi_team_gt_invariants_have_multi_team_roles(
    multi_team_bundle_dir: Path,
) -> None:
    gt = json.loads((multi_team_bundle_dir / "scenario.gt.json").read_text())
    inv = gt["invariants"]
    security_roles = inv["security_must_not_happen"][0]["forbidden_agent_roles"]
    assert "team_analyst" in security_roles
    assert "team_researcher" in security_roles


def test_resources_initial_mirror_exists(simple_bundle_dir: Path) -> None:
    ri = simple_bundle_dir / "resources_initial"
    assert ri.is_dir()
    # Should mirror resources/ structure
    assert (ri / "shared" / "market" / "snapshot.json").is_file()
    assert (ri / "shared" / "CLUB-ALPHA" / "club.sqlite").is_file()


def test_per_member_personal_sqlite(simple_bundle_dir: Path) -> None:
    agents_dir = simple_bundle_dir / "resources" / "agents"
    scenario_members = ["alice", "bob", "carol"]
    for mid in scenario_members:
        db_path = agents_dir / mid / "db" / "personal.sqlite"
        assert db_path.is_file(), f"Missing personal.sqlite for {mid}"
        with sqlite3.connect(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            assert "holdings" in tables
            assert "trade_history" in tables


def test_multi_team_gt_has_cross_team_privacy(
    multi_team_bundle_dir: Path,
) -> None:
    gt = json.loads((multi_team_bundle_dir / "scenario.gt.json").read_text())
    inv = gt["invariants"]
    privacy = inv["privacy_must_not_cross"]
    # Should have both portfolio and analyst_notes privacy rules
    sources = [p.get("source_scope", "") for p in privacy]
    assert any("analyst_notes" in s for s in sources)
    assert any("portfolio" in s for s in sources)
