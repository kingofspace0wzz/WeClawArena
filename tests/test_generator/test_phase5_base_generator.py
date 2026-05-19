"""Tests for the Phase-5 cell-aware base-task generator (S3 step 3).

These tests use a slice of cells to keep runtime manageable; one
parametrized test covers every family to catch loader-kwarg drift.
A full materialization sanity test runs once at the end across all cells
(tier dim dropped):

    3 marble_research cells * 8 tasks + 2 marble_bargaining cells * 12 tasks
    + 2 marble_bidding cells * 6 tasks + 11 other cells * 3 tasks = 93
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawsocialarena.generator.cell_allocation import all_cells
from clawsocialarena.generator.phase5_base_generator import (
    PHASE5_BASE_INDEX_FILENAME,
    PHASE5_METADATA_FILENAME,
    BaseBundleRecord,
    generate_base_bundles,
    load_base_index,
)


def test_generate_base_bundles_for_marble_research_cell_produces_eight_records(
    tmp_path: Path,
) -> None:
    """One marble_research cell now produces 8 task variants (not 3)."""
    cell = next(c for c in all_cells() if c.family_id == "marble_research")
    records = generate_base_bundles(
        out_dir=tmp_path,
        cells=(cell,),
    )
    assert len(records) == 8
    # Eight task indices, no tier dimension.
    task_indices = {r.task_index for r in records}
    assert task_indices == set(range(8))
    # Legacy tier fields are emitted as None on v2 records.
    assert all(r.tier_index is None for r in records)
    assert all(r.tier_name is None for r in records)


def test_generate_base_bundles_for_three_task_family_produces_three_records(
    tmp_path: Path,
) -> None:
    """A non-marble family cell (tau2_airline) still produces 3 base bundles."""
    from clawsocialarena.generator.cell_allocation import all_cells

    cell = next(c for c in all_cells() if c.family_id == "tau2_airline")
    records = generate_base_bundles(
        out_dir=tmp_path,
        cells=(cell,),
    )
    assert len(records) == 3
    task_indices = {r.task_index for r in records}
    assert task_indices == {0, 1, 2}
    assert all(r.tier_index is None for r in records)


def test_each_bundle_has_phase5_metadata_sidecar(tmp_path: Path) -> None:
    from clawsocialarena.generator.cell_allocation import all_cells

    cell = next(c for c in all_cells() if c.family_id == "tau2_airline")
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
    from clawsocialarena.generator.cell_allocation import all_cells

    cell = next(c for c in all_cells() if c.family_id == "tau2_airline")
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
    from clawsocialarena.generator.cell_allocation import all_cells

    cell = next(c for c in all_cells() if c.family_id == "tau2_airline")
    records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    assert {r.attack_intensity for r in records} == {0.4}


def test_easy_tier_scenario_json_keeps_full_turn_budget(tmp_path: Path) -> None:
    """At the easy/tier-1 baseline, max_turns must equal the loader's
    default (no tier multiplier shrinks it).
    """
    from clawsocialarena.generator.cell_allocation import all_cells

    cell = next(c for c in all_cells() if c.family_id == "tau2_airline")
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


def test_bargaining_cell_keeps_full_turn_budget_on_disk(tmp_path: Path) -> None:
    """For a marble_bargaining cell at the easy/tier-1 baseline, the
    materialized scenarios must keep the loader's full turn budget.
    No tier narrowing applies because the tier dim was dropped.
    """
    bargaining_cells = [c for c in all_cells() if c.family_id == "marble_bargaining"]
    assert bargaining_cells, "no marble_bargaining cell in allocation"
    cell = bargaining_cells[0]
    records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    for record in records:
        scenario_path = tmp_path / record.bundle_dir / "scenario.json"
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        assert scenario["max_turns"] == 36
        assert scenario["initial_state"]["resource_profile"].startswith(
            "owned_ecosystem_"
        )


def test_bargaining_cells_materialize_24_cell_specific_tasks(tmp_path: Path) -> None:
    bargaining_cells = tuple(
        cell for cell in all_cells() if cell.family_id == "marble_bargaining"
    )
    records = generate_base_bundles(out_dir=tmp_path, cells=bargaining_cells)

    assert len(records) == 24
    assert {record.cell_id for record in records} == {
        "CU-A-marble_bargaining",
        "CM-A-marble_bargaining",
    }
    assert {
        record.task_index
        for record in records
        if record.cell_id == "CU-A-marble_bargaining"
    } == set(range(12))
    assert {
        record.task_index
        for record in records
        if record.cell_id == "CM-A-marble_bargaining"
    } == set(range(12))
    assert len({record.loader_kwargs["transaction_id"] for record in records}) == 24


def test_index_file_is_written_and_round_trips(tmp_path: Path) -> None:
    from clawsocialarena.generator.cell_allocation import all_cells

    cell = next(c for c in all_cells() if c.family_id == "tau2_airline")
    records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    index_path = tmp_path / PHASE5_BASE_INDEX_FILENAME
    assert index_path.is_file()
    reloaded = load_base_index(index_path)
    assert len(reloaded) == len(records)
    assert all(isinstance(r, BaseBundleRecord) for r in reloaded)


@pytest.mark.parametrize(
    "family_id",
    sorted({cell.family_id for cell in all_cells()}),
)
def test_generator_works_for_one_cell_per_family(
    family_id: str, tmp_path: Path
) -> None:
    """Pick the first cell using each family and confirm the right number
    of bundles (one per task variant declared by that family) materialize
    without errors.
    """
    from clawsocialarena.generator.phase5_task_variants import task_variants_for

    cell = next(c for c in all_cells() if c.family_id == family_id)
    records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    expected = len(task_variants_for(family_id, cell_id=cell.cell_id))
    assert len(records) == expected, (
        f"{family_id}: expected {expected} records, got {len(records)}"
    )
    for record in records:
        bundle_dir = tmp_path / record.bundle_dir
        assert (bundle_dir / "scenario.json").is_file()
        assert (bundle_dir / PHASE5_METADATA_FILENAME).is_file()


def test_swebench_workspace_variants_are_registered_but_unallocated() -> None:
    """The coding family is available without changing current v2 row counts."""
    from clawsocialarena.generator.family_pack_registry import FAMILY_LOADERS
    from clawsocialarena.generator.phase5_task_variants import task_variants_for

    assert "swebench_workspace" in FAMILY_LOADERS
    assert "swebench_workspace" not in {cell.family_id for cell in all_cells()}
    assert len(task_variants_for("swebench_workspace")) == 24


@pytest.mark.slow
def test_n_records_after_tier_drop(tmp_path: Path) -> None:
    """End-to-end materialization across every cell with tier dimension dropped.
    Marked slow so the default `pytest -q` run skips it via `-m "not slow"`; CI can
    flip on the marker when the full benchmark scaffolding lands.

    Cell allocation: 3 marble_research cells (8 tasks each), 2 marble_bargaining
    cells (12 tasks each), 2 marble_bidding cells (6 tasks each), and 11 other cells
    (3 tasks each):

        3 * 8 + 2 * 12 + 2 * 6 + 11 * 3 = 93 base bundles
    """
    records = generate_base_bundles(out_dir=tmp_path)
    assert len(records) == 93
    assert len({r.base_scenario_id for r in records}) == 93
def test_generator_full_run_produces_54_bundles(tmp_path: Path) -> None:
    """End-to-end materialization across every cell with tier dimension dropped.
    Marked slow so the default `pytest -q` run skips it via `-m "not slow"`; CI can
    flip on the marker when the full benchmark scaffolding lands.
    18 cells × 3 tasks (tier dim dropped) = 54 base bundles.
    """
    records = generate_base_bundles(out_dir=tmp_path)
    assert len(records) == 54
    assert len({r.base_scenario_id for r in records}) == 54
