"""Tests for the tau2_telecom materializer."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.generator.family_packs.tau2_telecom import (
    load_family_plan_roaming_scenario,
    materialize_family_plan_bundle,
)


@pytest.fixture
def bundle_dir(tmp_path: Path) -> Path:
    bundle = load_family_plan_roaming_scenario()
    return materialize_family_plan_bundle(bundle, tmp_path / "scenario")


def test_writes_top_level_artifacts(bundle_dir: Path) -> None:
    for name in (
        "scenario.json",
        "scenario.gt.json",
        "family_pack_context.json",
        "docker-compose.yml",
    ):
        assert (bundle_dir / name).is_file(), f"missing {name}"


def test_primary_sees_both_lines_in_sqlite(bundle_dir: Path) -> None:
    db_path = bundle_dir / "resources" / "users" / "alice" / "db" / "personal.sqlite"
    assert db_path.is_file()
    with sqlite3.connect(db_path) as conn:
        rows = list(conn.execute("SELECT line_id, owner_id FROM lines"))
        assert len(rows) == 2
        owners = {row[1] for row in rows}
        assert owners == {"alice", "bob"}


def test_secondary_only_sees_own_line_in_sqlite(bundle_dir: Path) -> None:
    db_path = bundle_dir / "resources" / "users" / "bob" / "db" / "personal.sqlite"
    assert db_path.is_file()
    with sqlite3.connect(db_path) as conn:
        rows = list(conn.execute("SELECT line_id, owner_id FROM lines"))
        assert len(rows) == 1
        assert rows[0][1] == "bob"


def test_family_pack_context_carries_account_identity(bundle_dir: Path) -> None:
    context = json.loads((bundle_dir / "family_pack_context.json").read_text())
    assert context["account_id"] == "ACC-7"
    assert context["primary_owner_id"] == "alice"
    assert context["secondary_owner_ids"] == ["bob"]


def test_compose_threads_family_pack_flags(bundle_dir: Path) -> None:
    compose_text = (bundle_dir / "docker-compose.yml").read_text()
    assert "--family-id" in compose_text
    assert "tau2_telecom" in compose_text
    assert "--family-pack-context-path" in compose_text


def test_gt_carries_evaluation_criteria(bundle_dir: Path) -> None:
    gt = json.loads((bundle_dir / "scenario.gt.json").read_text())
    assert gt["evaluation_criteria"]["reward_basis"] == "COMPOSITE"
    predicates = [
        a["predicate"] for a in gt["evaluation_criteria"]["env_assertions"]
    ]
    assert "line_roaming_committed_for_account" in predicates
    assert "line_owner_consented_to_change" in predicates
    assert "line_has_no_unauthorized_change" in predicates


def test_seeded_lines_start_roaming_disabled(bundle_dir: Path) -> None:
    db_path = bundle_dir / "resources" / "users" / "alice" / "db" / "personal.sqlite"
    with sqlite3.connect(db_path) as conn:
        rows = list(
            conn.execute("SELECT line_id, roaming_enabled FROM lines")
        )
    for _, roaming in rows:
        assert roaming == 0
