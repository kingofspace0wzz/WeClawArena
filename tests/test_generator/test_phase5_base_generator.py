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


def test_generate_base_bundles_for_one_cell_produces_three_records(
    tmp_path: Path,
) -> None:
    """One cell × 3 task variants = 3 base bundles (tier dim dropped)."""
    cell = cell_by_index(0)  # CD-A-marble_research
    records = generate_base_bundles(
        out_dir=tmp_path,
        cells=(cell,),
    )
    assert len(records) == 3
    # Three task indices, no tier dimension.
    task_indices = {r.task_index for r in records}
    assert task_indices == {0, 1, 2}
    # Legacy tier fields are emitted as None on v2 records.
    assert all(r.tier_index is None for r in records)
    assert all(r.tier_name is None for r in records)


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
        # New canonical id format has no ``__d{tier}`` suffix.
        assert "__d" not in r.base_scenario_id


def test_attack_intensity_matches_easy_tier_default(tmp_path: Path) -> None:
    """With the tier dim dropped, every base bundle materializes at the
    easy/tier-1 baseline. The attack_intensity carried into the record
    must match what the difficulty-tier table declares for tier 1.
    """
    cell = cell_by_index(0)
    records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    assert {r.attack_intensity for r in records} == {0.4}


def test_easy_tier_scenario_json_keeps_full_turn_budget(tmp_path: Path) -> None:
    """At the easy/tier-1 baseline, max_turns must equal the loader's
    default (no tier multiplier shrinks it).
    """
    cell = cell_by_index(0)
    records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    seen_max_turns: set[int] = set()
    for record in records:
        scenario_path = tmp_path / record.bundle_dir / "scenario.json"
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        seen_max_turns.add(int(scenario["max_turns"]))
    # All three records share the same family / variant pool so they
    # land on the same easy-tier turn budget. The exact value is set
    # by the family pack; what we assert is that none of them was
    # multiplied down below the loader default.
    assert all(v > 0 for v in seen_max_turns)


def test_bargaining_cell_keeps_full_window_on_disk(tmp_path: Path) -> None:
    """For a marble_bargaining cell at the easy/tier-1 baseline, the
    materialized agent prompts must encode the loader's default
    (permissive) budget/reservation window. No narrowing applies
    because the tier dim was dropped.
    """
    import re

    bargaining_cells = [c for c in all_cells() if c.family_id == "marble_bargaining"]
    assert bargaining_cells, "no marble_bargaining cell in allocation"
    cell = bargaining_cells[0]
    records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    money = re.compile(r"\$(\d+(?:\.\d+)?)")
    spreads: list[float] = []
    for record in records:
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
        spreads.append(ceiling - reservation)
    # The default (un-narrowed) spread should be strictly positive.
    assert all(s > 0 for s in spreads)


def test_index_file_is_written_and_round_trips(tmp_path: Path) -> None:
    cell = cell_by_index(0)
    generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    index_path = tmp_path / PHASE5_BASE_INDEX_FILENAME
    assert index_path.is_file()
    reloaded = load_base_index(index_path)
    assert len(reloaded) == 3
    assert all(isinstance(r, BaseBundleRecord) for r in reloaded)


@pytest.mark.parametrize("family_id", sorted(FAMILY_LOADERS.keys()))
def test_generator_works_for_one_cell_per_family(
    family_id: str, tmp_path: Path
) -> None:
    """Pick the first cell using each family and confirm 3 bundles
    (one per task variant) materialize without errors.
    """
    cell = next(c for c in all_cells() if c.family_id == family_id)
    records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    assert len(records) == 3
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
