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
    load_cross_account_scenario,
    load_shared_account_scenario,
    materialize_cross_account_bundle,
    materialize_shared_account_bundle,
)


@pytest.fixture
def materialized_bundle(tmp_path: Path) -> Path:
    bundle = load_shared_account_scenario()
    return materialize_shared_account_bundle(bundle, tmp_path / "scenario")


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


def test_materialize_resources_writes_per_agent_sqlite(
    materialized_bundle: Path,
) -> None:
    """The materializer must produce one personal.sqlite per agent owner
    under the new canonical layout (resources/agents/<owner>/db/)."""
    alice_db = materialized_bundle / "resources/agents/alice/db/personal.sqlite"
    bob_db = materialized_bundle / "resources/agents/bob/db/personal.sqlite"
    assert alice_db.is_file()
    assert bob_db.is_file()

    conn = sqlite3.connect(alice_db)
    try:
        rows = conn.execute("SELECT pm_id FROM payment_methods").fetchall()
    finally:
        conn.close()
    assert rows, "alice's personal.sqlite should carry at least one payment method"


def test_materialize_shared_sqlite_is_written(
    materialized_bundle: Path,
) -> None:
    """The materializer must produce a shared SQLite for the shared account orders."""
    shared_sqlite = materialized_bundle / "resources/shared/HH-7/shared_account_orders.sqlite"
    assert shared_sqlite.is_file()
    conn = sqlite3.connect(shared_sqlite)
    try:
        rows = conn.execute("SELECT order_id FROM orders").fetchall()
    finally:
        conn.close()
    assert rows, "shared_account_orders.sqlite should carry at least one order"


def test_materialize_idempotent_on_rerun(tmp_path: Path) -> None:
    """Calling the materializer twice on the same out_dir overwrites
    cleanly without leaving stale files."""
    bundle = load_shared_account_scenario()
    out_dir = tmp_path / "scenario"
    materialize_shared_account_bundle(bundle, out_dir)
    first_pass = sorted(p.relative_to(out_dir).as_posix() for p in out_dir.rglob("*"))
    materialize_shared_account_bundle(bundle, out_dir)
    second_pass = sorted(p.relative_to(out_dir).as_posix() for p in out_dir.rglob("*"))
    assert first_pass == second_pass


def test_materialize_all_six_shared_account_tasks(tmp_path: Path) -> None:
    for i in range(6):
        bundle = load_shared_account_scenario(task_index=i)
        out_dir = materialize_shared_account_bundle(bundle, tmp_path / f"t{i}")
        assert (out_dir / "scenario.json").is_file()
        assert (out_dir / "scenario.gt.json").is_file()
        assert (out_dir / "family_pack_context.json").is_file()
        assert (out_dir / "resources" / "agents" / "alice" / "db" / "personal.sqlite").is_file()
        assert (out_dir / "resources" / "agents" / "bob" / "db" / "personal.sqlite").is_file()
        # The first 5 base tasks use HH-7 (seed default); t5 may use a different
        # shared_account_id per the seed. Look up the actual id from the bundle.
        shared_id = bundle.family_pack_context["shared_account_id"]
        assert (out_dir / "resources" / "shared" / shared_id / "shared_account_orders.sqlite").is_file()


def test_materialized_family_pack_context_has_archetype_field(tmp_path: Path) -> None:
    bundle = load_shared_account_scenario(task_index=0)
    out_dir = materialize_shared_account_bundle(bundle, tmp_path / "t0")
    ctx = json.loads((out_dir / "family_pack_context.json").read_text())
    assert ctx["archetype"] == "shared_account"
    assert ctx["tau2_source_task_id"] == "0"  # tau2#0 for t0


def test_materialized_personal_files_present(tmp_path: Path) -> None:
    bundle = load_shared_account_scenario(task_index=0)
    out_dir = materialize_shared_account_bundle(bundle, tmp_path / "t0")
    # Primary owner has shared_account_rules.md and secondary_spending_cap.md
    assert (out_dir / "resources" / "agents" / "alice" / "files" / "shared_account_rules.md").is_file()
    assert (out_dir / "resources" / "agents" / "alice" / "files" / "secondary_spending_cap.md").is_file()
    # Secondary owner has untrusted shopping notes file
    assert (out_dir / "resources" / "agents" / "bob" / "files").is_dir()


def test_materialize_all_six_cross_account_tasks(tmp_path: Path) -> None:
    for i in range(6):
        bundle = load_cross_account_scenario(task_index=i)
        out_dir = materialize_cross_account_bundle(bundle, tmp_path / f"t{i}")
        assert (out_dir / "scenario.json").is_file()
        assert (out_dir / "scenario.gt.json").is_file()
        assert (out_dir / "family_pack_context.json").is_file()
        # cross_account has NO shared/ dir
        assert not (out_dir / "resources" / "shared").exists()
        # both owners have personal DBs
        assert (out_dir / "resources" / "agents" / "carla" / "db" / "personal.sqlite").is_file()
        assert (out_dir / "resources" / "agents" / "diego" / "db" / "personal.sqlite").is_file()
        # representative untrusted and protected files
        assert (out_dir / "resources" / "agents" / "carla" / "files" / "gift_message.md").is_file()
        assert (out_dir / "resources" / "agents" / "diego" / "files" / "address_consent_policy.md").is_file()


def test_materialized_cross_account_family_pack_context_has_no_shared_account(tmp_path: Path) -> None:
    bundle = load_cross_account_scenario(task_index=0)
    out_dir = materialize_cross_account_bundle(bundle, tmp_path / "t0")
    ctx = json.loads((out_dir / "family_pack_context.json").read_text())
    assert ctx["archetype"] == "cross_account"
    assert ctx["no_shared_account"] is True
