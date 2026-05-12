"""Tests for the marble_bargaining materializer."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.generator.family_packs.marble_bargaining import (
    load_bargaining_scenario,
    materialize_bargaining_bundle,
)


@pytest.fixture
def bundle_dir(tmp_path: Path) -> Path:
    bundle = load_bargaining_scenario()
    return materialize_bargaining_bundle(bundle, tmp_path / "scenario")


def test_writes_top_level_artifacts(bundle_dir: Path) -> None:
    for name in (
        "scenario.json",
        "scenario.gt.json",
        "family_pack_context.json",
        "docker-compose.yml",
    ):
        assert (bundle_dir / name).is_file()


def test_each_agent_has_own_constraint_in_sqlite(bundle_dir: Path) -> None:
    buyer_db = bundle_dir / "resources" / "agents" / "alice" / "db" / "personal.sqlite"
    seller_db = bundle_dir / "resources" / "agents" / "bob" / "db" / "personal.sqlite"
    assert buyer_db.is_file() and seller_db.is_file()
    with sqlite3.connect(buyer_db) as conn:
        row = conn.execute(
            "SELECT budget_ceiling, reservation_price FROM private_constraints"
        ).fetchone()
        assert row[0] is not None  # buyer has a budget
        assert row[1] is None  # buyer has no reservation
    with sqlite3.connect(seller_db) as conn:
        row = conn.execute(
            "SELECT budget_ceiling, reservation_price FROM private_constraints"
        ).fetchone()
        assert row[0] is None
        assert row[1] is not None


def test_family_pack_context_carries_constraints(bundle_dir: Path) -> None:
    context = json.loads((bundle_dir / "family_pack_context.json").read_text())
    assert context["item_id"] == "ITEM-7"
    assert context["buyer_owner_id"] == "alice"
    assert context["seller_owner_id"] == "bob"
    assert context["buyer_budget_ceiling"] > context["seller_reservation"]


def test_compose_threads_family_pack_flags(bundle_dir: Path) -> None:
    compose_text = (bundle_dir / "docker-compose.yml").read_text()
    assert "marble_bargaining" in compose_text
    assert "--family-pack-context-path" in compose_text


def test_gt_carries_evaluation_criteria(bundle_dir: Path) -> None:
    gt = json.loads((bundle_dir / "scenario.gt.json").read_text())
    predicates = [
        a["predicate"] for a in gt["evaluation_criteria"]["env_assertions"]
    ]
    assert "agreement_recorded_for_item" in predicates
    assert "agreed_price_within_window" in predicates
