"""Tests for tau2_retail bundle materialization.

Validates the Phase 3 follow-on: turning the in-memory
HouseholdScenarioBundle into an on-disk bundle that matches the v2
layout (scenario.json, scenario.gt.json, docker-compose.yml,
personas/, mcp/, governance/, resources/).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.generator.family_packs.tau2_retail import (
    load_household_exchange_scenario,
    materialize_household_bundle,
)


@pytest.fixture
def materialized_bundle(tmp_path: Path) -> Path:
    bundle = load_household_exchange_scenario()
    return materialize_household_bundle(bundle, tmp_path / "scenario")


def test_materialize_writes_required_files(materialized_bundle: Path) -> None:
    """The bundle must include every artifact the v2 layout requires."""
    for relative in (
        "scenario.json",
        "scenario.gt.json",
        "docker-compose.yml",
        "personas/alice_assistant.system.md",
        "personas/alice_assistant.tools.json",
        "personas/bob_assistant.system.md",
        "personas/bob_assistant.tools.json",
        "governance/manifest.json",
    ):
        assert (materialized_bundle / relative).is_file(), f"missing {relative}"


def test_materialize_scenario_json_carries_topology_fields(
    materialized_bundle: Path,
) -> None:
    data = json.loads((materialized_bundle / "scenario.json").read_text())
    assert data["family_id"] == "tau2_retail"
    assert data["coordination_mode"] == "graph"
    assert "agent_graph" in data
    assert len(data["agent_graph"]["nodes"]) == 2


def test_materialize_scenario_gt_json_uses_evaluation_criteria(
    materialized_bundle: Path,
) -> None:
    """The new task-contract shape replaces terminal_predicate with
    evaluation_criteria. The QC aggregator looks for reward_basis here."""
    gt = json.loads((materialized_bundle / "scenario.gt.json").read_text())
    assert "evaluation_criteria" in gt
    assert "terminal_predicate" not in gt
    assert gt["evaluation_criteria"]["reward_basis"] == "COMPOSITE"


def test_materialize_governance_manifest_carries_two_owners(
    materialized_bundle: Path,
) -> None:
    manifest = json.loads((materialized_bundle / "governance/manifest.json").read_text())
    assert set(manifest["owners"].keys()) == {"alice", "bob"}
    assert "relationships" in manifest


def test_materialize_persona_files_carry_role_header(
    materialized_bundle: Path,
) -> None:
    primary = (materialized_bundle / "personas/alice_assistant.system.md").read_text()
    secondary = (materialized_bundle / "personas/bob_assistant.system.md").read_text()
    assert "primary_account_holder" in primary
    assert "secondary_account_holder" in secondary
    assert "Active identity" in primary
    assert "Active identity" in secondary


def test_materialize_mcp_stubs_cover_declared_tool_surface(
    materialized_bundle: Path,
) -> None:
    """Stubs only (full MCP wrappers are the next milestone), but the
    declared tool surface from evaluation_criteria.actions must be
    represented so the bundle layout passes structural validation."""
    mcp_dir = materialized_bundle / "mcp"
    files = {p.name for p in mcp_dir.iterdir() if p.suffix == ".json"}
    assert "exchange_item.json" in files
    assert "find_user_id_by_name_zip.json" in files
    assert "get_order_details.json" in files
    for stub_path in mcp_dir.iterdir():
        stub = json.loads(stub_path.read_text())
        assert stub["status"] == "stub", (
            f"{stub_path.name} should be marked as a stub until the "
            "MCP wrapper layer lands"
        )


def test_materialize_resources_writes_per_user_sqlite(
    materialized_bundle: Path,
) -> None:
    """The database slicing adapter must produce one personal.sqlite
    per household member, each carrying the household's orders."""
    alice_db = materialized_bundle / "resources/users/alice/db/personal.sqlite"
    bob_db = materialized_bundle / "resources/users/bob/db/personal.sqlite"
    assert alice_db.is_file()
    assert bob_db.is_file()

    conn = sqlite3.connect(alice_db)
    try:
        rows = conn.execute("SELECT order_id, household_id FROM orders").fetchall()
    finally:
        conn.close()
    assert rows, "alice's personal.sqlite should carry at least one order"
    for _, household_id in rows:
        assert household_id == "HH-7"


def test_materialize_household_orders_json_is_written(
    materialized_bundle: Path,
) -> None:
    orders_path = materialized_bundle / "resources/household/HH-7/orders.json"
    assert orders_path.is_file()
    orders = json.loads(orders_path.read_text())
    assert isinstance(orders, list)
    assert len(orders) >= 1
    for order in orders:
        assert order["household_id"] == "HH-7"


def test_materialize_idempotent_on_rerun(tmp_path: Path) -> None:
    """Calling the materializer twice on the same out_dir overwrites
    cleanly without leaving stale files."""
    bundle = load_household_exchange_scenario()
    out_dir = tmp_path / "scenario"
    materialize_household_bundle(bundle, out_dir)
    first_pass = sorted(p.relative_to(out_dir).as_posix() for p in out_dir.rglob("*"))
    materialize_household_bundle(bundle, out_dir)
    second_pass = sorted(p.relative_to(out_dir).as_posix() for p in out_dir.rglob("*"))
    assert first_pass == second_pass
