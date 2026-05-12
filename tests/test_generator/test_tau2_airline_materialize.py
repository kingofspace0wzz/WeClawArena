"""Tests for the tau2_airline materializer."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.generator.family_packs.tau2_airline import (
    load_group_seat_change_scenario,
    materialize_group_booking_bundle,
)


@pytest.fixture
def bundle_dir(tmp_path: Path) -> Path:
    bundle = load_group_seat_change_scenario()
    return materialize_group_booking_bundle(bundle, tmp_path / "scenario")


def test_writes_top_level_artifacts(bundle_dir: Path) -> None:
    for name in (
        "scenario.json",
        "scenario.gt.json",
        "family_pack_context.json",
        "docker-compose.yml",
    ):
        assert (bundle_dir / name).is_file(), f"missing {name}"


def test_writes_personas_and_tool_manifests(bundle_dir: Path) -> None:
    personas_dir = bundle_dir / "personas"
    assert (personas_dir / "alice_organizer.system.md").is_file()
    assert (personas_dir / "bob_traveler.system.md").is_file()
    organizer_tools = json.loads(
        (personas_dir / "alice_organizer.tools.json").read_text()
    )
    assert "commit_seat_change" in organizer_tools
    assert "consent_to_seat_change" in organizer_tools


def test_per_passenger_sqlite_has_reservation_row(bundle_dir: Path) -> None:
    for owner in ("alice", "bob"):
        db_path = bundle_dir / "resources" / "passengers" / owner / "db" / "personal.sqlite"
        assert db_path.is_file(), f"missing sqlite for {owner}"
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT reservation_id, group_id, passengers FROM reservations"
            ).fetchone()
            assert row is not None
            assert row[1] == "GRP-7"
            passengers = json.loads(row[2])
            roles = {p["role"] for p in passengers}
            assert {"organizer", "traveler"}.issubset(roles)


def test_family_pack_context_carries_group_identity(bundle_dir: Path) -> None:
    context = json.loads((bundle_dir / "family_pack_context.json").read_text())
    assert context["group_id"] == "GRP-7"
    assert context["organizer_owner_id"] == "alice"
    assert context["traveler_owner_ids"] == ["bob"]


def test_compose_threads_family_pack_flags(bundle_dir: Path) -> None:
    compose_text = (bundle_dir / "docker-compose.yml").read_text()
    assert "--family-id" in compose_text
    assert "tau2_airline" in compose_text
    assert "--family-pack-context-path" in compose_text
    assert "./family_pack_context.json:/workspace/family_pack_context.json:ro" in compose_text


def test_gt_carries_evaluation_criteria(bundle_dir: Path) -> None:
    gt = json.loads((bundle_dir / "scenario.gt.json").read_text())
    assert gt["evaluation_criteria"]["reward_basis"] == "COMPOSITE"
    predicates = [
        a["predicate"] for a in gt["evaluation_criteria"]["env_assertions"]
    ]
    assert "group_reservation_seat_committed" in predicates
    assert "passenger_consented_to_change" in predicates
