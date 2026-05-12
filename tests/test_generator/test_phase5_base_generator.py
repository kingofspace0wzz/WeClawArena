"""Tests for the Phase-5 cell-aware base-task generator (S3 step 3).

These tests use a slice of cells to keep runtime manageable; one
parametrized test covers every family to catch loader-kwarg drift.
A full 42-bundle materialization sanity test runs once at the end
with a short tmp_path (14 cells x 3 tasks, tier dim dropped).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawsocialarena.generator.cell_allocation import all_cells, cell_by_index
from clawsocialarena.generator.family_pack_registry import FAMILY_LOADERS
from clawsocialarena.generator.phase5_base_generator import (
    PHASE5_BASE_INDEX_FILENAME,
    PHASE5_METADATA_FILENAME,
    BaseBundleRecord,
    generate_base_bundles,
    load_base_index,
)


def test_generate_base_bundles_for_one_cell_produces_nine_records(
    tmp_path: Path,
) -> None:
    """One cell × 3 task variants × 3 tiers = 9 base bundles."""
    cell = cell_by_index(0)  # CD-A-marble_research
    records = generate_base_bundles(
        out_dir=tmp_path,
        cells=(cell,),
    )
    assert len(records) == 9
    # Three task indices, each with three tiers.
    pairs = {(r.task_index, r.tier_index) for r in records}
    assert pairs == {(t, d) for t in (0, 1, 2) for d in (1, 2, 3)}


def test_each_bundle_has_phase5_metadata_sidecar(tmp_path: Path) -> None:
    cell = cell_by_index(0)
    records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    for record in records:
        sidecar = tmp_path / record.bundle_dir / PHASE5_METADATA_FILENAME
        assert sidecar.is_file(), f"missing sidecar for {record.base_scenario_id}"
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        assert payload["cell"]["cell_id"] == record.cell_id
        assert payload["task_variant"]["task_index"] == record.task_index
        assert payload["tier"]["tier_index"] == record.tier_index
        assert payload["base_scenario_id"] == record.base_scenario_id


def test_base_scenario_ids_are_unique(tmp_path: Path) -> None:
    cell = cell_by_index(0)
    records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    ids = [r.base_scenario_id for r in records]
    assert len(set(ids)) == len(ids)
    for r in records:
        assert r.base_scenario_id.startswith(r.cell_id)


def test_tier_intensity_matches_difficulty_table(tmp_path: Path) -> None:
    """The attack_intensity carried into the record must match what the
    difficulty-tier table declares for that tier.
    """
    cell = cell_by_index(0)
    records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    by_tier = {r.tier_index: r.attack_intensity for r in records if r.task_index == 0}
    assert by_tier == {1: 0.4, 2: 0.6, 3: 0.8}


def test_tier_overlay_modifies_scenario_json_max_turns(tmp_path: Path) -> None:
    """Tier 3 (stress) should produce a strictly smaller max_turns
    than tier 1 (easy) for the same task variant. Higher tier =
    tighter turn budget = harder, per spec section 5.
    """
    cell = cell_by_index(0)
    records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    by_tier: dict[int, int] = {}
    for record in records:
        if record.task_index != 0:
            continue
        scenario_path = tmp_path / record.bundle_dir / "scenario.json"
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        by_tier[record.tier_index] = int(scenario["max_turns"])
    assert by_tier[1] > by_tier[2] > by_tier[3], (
        f"max_turns not strictly tightening across tiers: {by_tier}"
    )


def test_bargaining_cell_narrows_window_on_disk(tmp_path: Path) -> None:
    """For a marble_bargaining cell, the materialized agent prompts
    should encode a narrower budget/reservation window at tier 3
    than at tier 1. The loader bakes the dollar amounts into the
    buyer and seller system prompt templates.
    """
    import re

    bargaining_cells = [c for c in all_cells() if c.family_id == "marble_bargaining"]
    assert bargaining_cells, "no marble_bargaining cell in allocation"
    cell = bargaining_cells[0]
    records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    # Map tier_index -> (seller_reservation, buyer_budget_ceiling).
    win_by_tier: dict[int, tuple[float, float]] = {}
    money = re.compile(r"\$(\d+(?:\.\d+)?)")
    for record in records:
        if record.task_index != 0:
            continue
        scenario_path = tmp_path / record.bundle_dir / "scenario.json"
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        buyer_prompt = next(
            a["system_prompt_template"]
            for a in scenario["agents"]
            if a["agent_id"].endswith("_buyer")
        )
        seller_prompt = next(
            a["system_prompt_template"]
            for a in scenario["agents"]
            if a["agent_id"].endswith("_seller")
        )
        ceiling = float(money.search(buyer_prompt).group(1))
        reservation = float(money.search(seller_prompt).group(1))
        win_by_tier[record.tier_index] = (reservation, ceiling)
    spreads = {tier: hi - lo for tier, (lo, hi) in win_by_tier.items()}
    assert spreads[1] > spreads[2] > spreads[3], (
        f"bargaining window did not narrow per tier: {spreads}"
    )


def test_index_file_is_written_and_round_trips(tmp_path: Path) -> None:
    cell = cell_by_index(0)
    generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    index_path = tmp_path / PHASE5_BASE_INDEX_FILENAME
    assert index_path.is_file()
    reloaded = load_base_index(index_path)
    assert len(reloaded) == 9
    assert all(isinstance(r, BaseBundleRecord) for r in reloaded)


@pytest.mark.parametrize("family_id", sorted(FAMILY_LOADERS.keys()))
def test_generator_works_for_one_cell_per_family(
    family_id: str, tmp_path: Path
) -> None:
    """Pick the first cell using each family and confirm 9 bundles
    materialize without errors.
    """
    cell = next(c for c in all_cells() if c.family_id == family_id)
    records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    assert len(records) == 9
    for record in records:
        bundle_dir = tmp_path / record.bundle_dir
        assert (bundle_dir / "scenario.json").is_file()
        assert (bundle_dir / PHASE5_METADATA_FILENAME).is_file()


@pytest.mark.slow
def test_generator_full_run_produces_42_bundles(tmp_path: Path) -> None:
    """End-to-end materialization across every cell with tier dimension dropped.
    Marked slow so the default `pytest -q` run skips it via `-m "not slow"`; CI can
    flip on the marker when the full benchmark scaffolding lands.
    14 cells × 3 tasks (tier dim dropped) = 42 base bundles.
    """
    records = generate_base_bundles(out_dir=tmp_path)
    assert len(records) == 42
    assert len({r.base_scenario_id for r in records}) == 42
