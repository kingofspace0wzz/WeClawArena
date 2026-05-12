"""Tests for the wildclaw_social materializer."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.generator.family_packs.wildclaw_social import (
    load_meeting_negotiation_scenario,
    materialize_meeting_negotiation_bundle,
)


@pytest.fixture
def bundle_dir(tmp_path: Path) -> Path:
    bundle = load_meeting_negotiation_scenario()
    return materialize_meeting_negotiation_bundle(bundle, tmp_path / "scenario")


def test_writes_top_level_artifacts(bundle_dir: Path) -> None:
    for name in (
        "scenario.json",
        "scenario.gt.json",
        "family_pack_context.json",
        "docker-compose.yml",
    ):
        assert (bundle_dir / name).is_file()


def test_each_team_member_has_own_sqlite(bundle_dir: Path) -> None:
    for owner in ("alice", "bob", "carol", "dave"):
        db_path = bundle_dir / "resources" / "team" / owner / "db" / "personal.sqlite"
        assert db_path.is_file(), f"missing sqlite for {owner}"
        with sqlite3.connect(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            assert {"meetings", "availability", "inbox"}.issubset(tables)


def test_participants_have_seeded_availability(bundle_dir: Path) -> None:
    for owner in ("bob", "carol", "dave"):
        db_path = bundle_dir / "resources" / "team" / owner / "db" / "personal.sqlite"
        with sqlite3.connect(db_path) as conn:
            rows = list(
                conn.execute(
                    "SELECT day, start, end FROM availability WHERE owner_id = ?",
                    (owner,),
                )
            )
            assert rows
            assert rows[0][0] == "Thursday"


def test_family_pack_context_lists_participants(bundle_dir: Path) -> None:
    context = json.loads((bundle_dir / "family_pack_context.json").read_text())
    assert context["organizer_owner_id"] == "alice"
    assert set(context["participant_owner_ids"]) == {"bob", "carol", "dave"}


def test_compose_threads_family_pack_flags(bundle_dir: Path) -> None:
    compose_text = (bundle_dir / "docker-compose.yml").read_text()
    assert "wildclaw_social" in compose_text
    assert "--family-pack-context-path" in compose_text


def test_gt_carries_evaluation_criteria(bundle_dir: Path) -> None:
    gt = json.loads((bundle_dir / "scenario.gt.json").read_text())
    predicates = [
        a["predicate"] for a in gt["evaluation_criteria"]["env_assertions"]
    ]
    assert "meeting_event_created" in predicates
    assert "all_participants_confirmed_meeting" in predicates
