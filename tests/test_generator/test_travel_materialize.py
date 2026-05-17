"""Tests for the travel materializer (Task 4 of the travel first-ship plan)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.generator.family_packs.travel.loader import (
    load_travel_scenario,
)
from clawsocialarena.generator.family_packs.travel.materialize import (
    materialize_travel_bundle,
)


@pytest.fixture
def cu_bundle_dir(tmp_path: Path) -> Path:
    bundle = load_travel_scenario(
        trip_id="TRIP-CU-OE-001",
        resource_profile="owned_ecosystem_solo_business_yunnan",
    )
    return materialize_travel_bundle(bundle, tmp_path / "cu_bundle")


@pytest.fixture
def mg_bundle_dir(tmp_path: Path) -> Path:
    bundle = load_travel_scenario(
        trip_id="TRIP-MG-OE-101",
        resource_profile="owned_ecosystem_family_group_guizhou",
    )
    return materialize_travel_bundle(bundle, tmp_path / "mg_bundle")


# --- File presence ----------------------------------------------------------


def test_materialize_cu_creates_top_level_files(cu_bundle_dir: Path) -> None:
    for relative in [
        "scenario.json",
        "scenario.gt.json",
        "docker-compose.yml",
        "family_pack_context.json",
        "personas",
        "resources",
        "mcp",
    ]:
        assert (cu_bundle_dir / relative).exists(), f"missing {relative}"


def test_materialize_cu_writes_persona_per_agent(cu_bundle_dir: Path) -> None:
    personas = sorted((cu_bundle_dir / "personas").glob("*.system.md"))
    assert len(personas) == 3
    names = {p.name for p in personas}
    # Each of 3 agents must have a persona file
    scn = json.loads((cu_bundle_dir / "scenario.json").read_text())
    for agent in scn["agents"]:
        assert f"{agent['agent_id']}.system.md" in names


def test_materialize_mg_writes_persona_per_agent(mg_bundle_dir: Path) -> None:
    personas = sorted((mg_bundle_dir / "personas").glob("*.system.md"))
    assert len(personas) == 5  # organizer + 3 co + partner_hotel


def test_resources_mount_under_agents_subdir(cu_bundle_dir: Path) -> None:
    """The bargaining scaffold uses resources/agents/<agent_id>/...

    Codex review flagged this on rev 1; the rev 2 plan locks the layout
    explicitly. Verify travel matches.
    """
    scn = json.loads((cu_bundle_dir / "scenario.json").read_text())
    for agent in scn["agents"]:
        agent_dir = cu_bundle_dir / "resources" / "agents" / agent["agent_id"]
        assert agent_dir.is_dir(), f"missing {agent_dir}"
        assert (agent_dir / "files").is_dir()
        assert (agent_dir / "db" / "personal.sqlite").is_file()


def test_traveler_files_include_loyalty_and_medical(cu_bundle_dir: Path) -> None:
    """Per the family-pack-design spec section 4.7, traveler owns
    loyalty_status.json + medical_constraints.md + payment_methods.json
    at minimum."""
    scn = json.loads((cu_bundle_dir / "scenario.json").read_text())
    traveler_node = next(
        n for n in scn["agent_graph"]["nodes"] if n["role_label"] == "traveler"
    )
    files_dir = (
        cu_bundle_dir / "resources" / "agents" / traveler_node["agent_id"] / "files"
    )
    assert (files_dir / "loyalty_status.json").is_file()
    assert (files_dir / "medical_constraints.md").is_file()
    assert (files_dir / "payment_methods.json").is_file()
    assert (files_dir / "current_trip_state.json").is_file()


def test_partner_hotel_files_include_inventory_and_pricing(
    cu_bundle_dir: Path,
) -> None:
    scn = json.loads((cu_bundle_dir / "scenario.json").read_text())
    partner_node = next(
        n for n in scn["agent_graph"]["nodes"] if n["role_label"] == "partner_hotel"
    )
    files_dir = (
        cu_bundle_dir / "resources" / "agents" / partner_node["agent_id"] / "files"
    )
    assert (files_dir / "room_policies.md").is_file()
    assert (files_dir / "loyalty_partner_match.json").is_file()


def test_approver_files_include_corp_policy(cu_bundle_dir: Path) -> None:
    scn = json.loads((cu_bundle_dir / "scenario.json").read_text())
    approver_node = next(
        n for n in scn["agent_graph"]["nodes"] if n["role_label"] == "approver"
    )
    files_dir = (
        cu_bundle_dir / "resources" / "agents" / approver_node["agent_id"] / "files"
    )
    assert (files_dir / "corp_travel_policy.md").is_file()
    assert (files_dir / "delegate_authorization_codes.json").is_file()


def test_co_traveler_files_carry_distinct_lifts(mg_bundle_dir: Path) -> None:
    """Each co_traveler's loyalty_status.json should be derived from a
    distinct lift, so the materializer cannot accidentally clone all
    three from the same source."""
    scn = json.loads((mg_bundle_dir / "scenario.json").read_text())
    co_nodes = [
        n for n in scn["agent_graph"]["nodes"] if n["role_label"] == "co_traveler"
    ]
    assert len(co_nodes) == 3
    home_cities: set[str] = set()
    for node in co_nodes:
        loyalty_path = (
            mg_bundle_dir
            / "resources"
            / "agents"
            / node["agent_id"]
            / "files"
            / "loyalty_status.json"
        )
        loyalty = json.loads(loyalty_path.read_text())
        # Each lift maps to a distinct home_city; the materializer must
        # not coalesce them.
        home_cities.add(loyalty.get("home_city", ""))
    assert len(home_cities) == 3, f"only {len(home_cities)} distinct cities"


# --- scenario.gt.json shape -------------------------------------------------


def test_scenario_gt_evaluation_criteria_uses_canonical_schema(
    cu_bundle_dir: Path,
) -> None:
    gt = json.loads((cu_bundle_dir / "scenario.gt.json").read_text())
    ec = gt["evaluation_criteria"]
    allowed_keys = {
        "actions",
        "env_assertions",
        "communicate_info",
        "nl_assertions",
        "reward_basis",
    }
    assert set(ec.keys()).issubset(allowed_keys)
    assert "database_writes" not in ec
    assert ec["reward_basis"] in {"actions", "env_assertions", "mixed"}


def test_scenario_gt_governance_manifest_present(cu_bundle_dir: Path) -> None:
    gt = json.loads((cu_bundle_dir / "scenario.gt.json").read_text())
    assert "governance_manifest" in gt
    assert "resource_manifest" in gt
    assert "mcp_tool_manifest" in gt
    assert "persona_manifest" in gt


def test_scenario_gt_mcp_manifest_includes_travel_tools(cu_bundle_dir: Path) -> None:
    gt = json.loads((cu_bundle_dir / "scenario.gt.json").read_text())
    tool_names = set(gt["mcp_tool_manifest"].keys())
    # Per the family-pack-design spec section 4.7, ten travel tools ship
    # plus the standard scope-restricted file/db tools.
    expected_travel = {
        "search_hotels",
        "get_hotel_details",
        "place_booking_hold",
        "confirm_booking",
        "map_search_places",
        "map_compute_routes",
        "weather_forecast_days",
    }
    missing = expected_travel - tool_names
    assert not missing, f"missing travel tools: {missing}"


# --- family_pack_context.json ----------------------------------------------


def test_family_pack_context_carries_required_keys(cu_bundle_dir: Path) -> None:
    fpc = json.loads((cu_bundle_dir / "family_pack_context.json").read_text())
    required = {
        "trip_id",
        "resource_profile",
        "destination",
        "target_unit_rate",
        "partner_floor_rate",
        "traveler_owner_id",
        "partner_hotel_owner_id",
        "approver_owner_id",
        "delegate_authorization_code",
    }
    missing = required - set(fpc.keys())
    assert not missing, f"missing keys: {missing}"


def test_family_pack_context_mg_carries_group_keys(mg_bundle_dir: Path) -> None:
    fpc = json.loads((mg_bundle_dir / "family_pack_context.json").read_text())
    assert fpc["group_budget_envelope"] == 8000.0
    assert fpc["per_person_cap"] == 2200.0
    assert fpc["consensus_threshold"] == 4
    assert len(fpc["co_traveler_owner_ids"]) == 3


# --- sqlite DB content ------------------------------------------------------


def test_partner_inventory_db_has_seeded_rooms(cu_bundle_dir: Path) -> None:
    scn = json.loads((cu_bundle_dir / "scenario.json").read_text())
    partner_node = next(
        n for n in scn["agent_graph"]["nodes"] if n["role_label"] == "partner_hotel"
    )
    db_path = (
        cu_bundle_dir / "resources" / "agents" / partner_node["agent_id"]
        / "db" / "personal.sqlite"
    )
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT COUNT(*) FROM inventory"
        ).fetchone()
        assert rows[0] > 0, "no rows in inventory table"
        rows = conn.execute(
            "SELECT COUNT(*) FROM dynamic_pricing"
        ).fetchone()
        assert rows[0] > 0, "no rows in dynamic_pricing table"
    finally:
        conn.close()


def test_approver_approval_log_table_exists_but_empty(cu_bundle_dir: Path) -> None:
    """The approval_log is the write-only artifact; it must exist as a
    table but should start empty so the run can populate it."""
    scn = json.loads((cu_bundle_dir / "scenario.json").read_text())
    approver_node = next(
        n for n in scn["agent_graph"]["nodes"] if n["role_label"] == "approver"
    )
    db_path = (
        cu_bundle_dir / "resources" / "agents" / approver_node["agent_id"]
        / "db" / "personal.sqlite"
    )
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT COUNT(*) FROM approval_log").fetchone()
        assert rows[0] == 0
    finally:
        conn.close()
