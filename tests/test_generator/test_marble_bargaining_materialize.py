"""Tests for the marble_bargaining materializer.

Verifies that the three task-variant items (Toyota Corolla, MacBook Pro,
vinyl record collection) materialize with distinct item IDs and descriptions,
and that buyer/seller constraint databases are correctly written.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.generator.family_packs.marble_bargaining import (
    load_bargaining_scenario,
    materialize_bargaining_bundle,
)
from clawsocialarena.generator.phase5_task_variants import task_variants_for


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


@pytest.mark.parametrize("task_index, expected_item_id", [
    (0, "ITEM-7"),
    (1, "ITEM-12"),
    (2, "ITEM-21"),
])
def test_three_task_variants_produce_distinct_items(
    task_index: int,
    expected_item_id: str,
    tmp_path: Path,
) -> None:
    """Each task variant must materialize with its own item_id."""
    variants = task_variants_for("marble_bargaining")
    variant = variants[task_index]
    bundle = load_bargaining_scenario(**variant.loader_kwargs)
    out = tmp_path / f"task{task_index}"
    materialize_bargaining_bundle(bundle, out)
    scenario = json.loads((out / "scenario.json").read_text())
    assert scenario["initial_state"]["item_id"] == expected_item_id, (
        f"task {task_index} expected item_id={expected_item_id}"
    )
    # item_description must be non-trivial
    desc = scenario["initial_state"]["item_description"]
    assert len(desc) > 20


def test_all_three_item_ids_are_distinct(tmp_path: Path) -> None:
    """Materialized item IDs must be pairwise distinct across task variants."""
    variants = task_variants_for("marble_bargaining")
    item_ids: list[str] = []
    for i, variant in enumerate(variants):
        bundle = load_bargaining_scenario(**variant.loader_kwargs)
        out = tmp_path / f"task{i}"
        materialize_bargaining_bundle(bundle, out)
        scenario = json.loads((out / "scenario.json").read_text())
        item_ids.append(scenario["initial_state"]["item_id"])
    assert len(set(item_ids)) == 3, f"item_ids not distinct: {item_ids}"


def test_item_id_propagates_to_gt_evaluation_criteria(tmp_path: Path) -> None:
    """The gt evaluation criteria must reference the task-specific item_id."""
    variants = task_variants_for("marble_bargaining")
    for i, variant in enumerate(variants):
        bundle = load_bargaining_scenario(**variant.loader_kwargs)
        out = tmp_path / f"gt_task{i}"
        materialize_bargaining_bundle(bundle, out)
        gt = json.loads((out / "scenario.gt.json").read_text())
        expected_item_id = variant.loader_kwargs["item_id"]
        for action in gt["evaluation_criteria"]["actions"]:
            if "compare_args" in action:
                assert action.get("item_id", expected_item_id) == expected_item_id
        for assertion in gt["evaluation_criteria"]["env_assertions"]:
            assert assertion["args"]["item_id"] == expected_item_id, (
                f"task {i}: env_assertion item_id mismatch"
            )
