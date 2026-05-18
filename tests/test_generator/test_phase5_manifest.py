"""Tests for the Phase-5 manifest aggregator (S3 step 7).

These tests run on a partial allocation (one cell) to keep runtime
manageable. A separate full-manifest test is marked ``slow`` so the
default test command skips it. v2 math after bargaining, bidding, and
travel expansion:
  3 marble_research cells × 8 × 5 = 120
  2 marble_bargaining cells × 12 × 5 = 120
  2 marble_bidding cells × 6 × 5 = 60
  11 other cells × 3 × 5 = 165
  Total: 465 main + 50 supplementary = 515 rows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.generator.cell_allocation import cell_by_index
from clawsocialarena.generator.phase5_attack_variants import (
    expand_base_records_to_variants,
)
from clawsocialarena.generator.phase5_base_generator import (
    generate_base_bundles,
)
from clawsocialarena.generator.phase5_manifest import (
    EXPECTED_MAIN_VARIANTS,
    EXPECTED_SUPPLEMENTARY_VARIANTS,
    EXPECTED_TOTAL_VARIANTS,
    PHASE5_MANIFEST_FILENAME,
    assemble_manifest,
    load_manifest,
    select_rows,
)


def _build_full_manifest(out_dir: Path) -> dict:
    """Build the full 515-row manifest using all 18 allocated cells."""
    base_records = generate_base_bundles(out_dir=out_dir)
    expand_base_records_to_variants(base_records=base_records, base_dir=out_dir)
    return assemble_manifest(out_dir=out_dir, base_records=base_records)


def _build_one_cell_manifest(out_dir: Path) -> dict:
    """Build a partial manifest using one cell (for fast-path tests).

    The supplementary block is the same 50 rows regardless of which
    cells are used, and the main block scales linearly with cells.
    Bypasses the EXPECTED_MAIN_VARIANTS check in assemble_manifest by
    building the dict manually for partial runs.
    """
    cell = cell_by_index(0)
    base_records = generate_base_bundles(out_dir=out_dir, cells=(cell,))
    expand_base_records_to_variants(base_records=base_records, base_dir=out_dir)
    from clawsocialarena.generator.phase5_attack_variants import (
        PHASE5_VARIANT_INDEX_FILENAME,
        load_variant_index,
    )

    variants = load_variant_index(out_dir / PHASE5_VARIANT_INDEX_FILENAME)
    from dataclasses import asdict

    from clawsocialarena.generator.phase5_manifest import (
        _supp_records_to_manifest_rows,
        _variants_to_manifest_rows,
    )
    from clawsocialarena.generator.phase5_supplementary import (
        supplementary_records,
    )

    main_rows = _variants_to_manifest_rows(variants)
    supp_rows = _supp_records_to_manifest_rows(supplementary_records())
    return {
        "phase5_version": 1,
        "n_main": len(main_rows),
        "n_supplementary": len(supp_rows),
        "n_total": len(main_rows) + len(supp_rows),
        "main": [asdict(r) for r in main_rows],
        "supplementary": [asdict(r) for r in supp_rows],
    }


def test_select_rows_filters_by_task(tmp_path: Path) -> None:
    manifest = _build_one_cell_manifest(tmp_path)
    # cell_by_index(0) is CD-A-marble_research (8 tasks × 5 modes = 40 main rows).
    assert len(manifest["main"]) == 40
    # Smoke selection: task_index=0, 5 attack modes -> 5 rows.
    smoke = select_rows(manifest, stratum="main", task_index=0)
    assert len(smoke) == 5
    # Modes are the spec section 2 axis labels, not recipe names.
    modes = {row["attack_mode"] for row in smoke}
    assert modes == {
        "no_attacker",
        "collaboration",
        "security",
        "privacy",
        "governance",
    }


def test_select_rows_supplementary_only(tmp_path: Path) -> None:
    manifest = _build_one_cell_manifest(tmp_path)
    supp = select_rows(manifest, stratum="supplementary")
    assert len(supp) == EXPECTED_SUPPLEMENTARY_VARIANTS
    sub_set = {row["sub_stratum"] for row in supp}
    assert sub_set == {"hard_verification", "episode_graph", "named_audit"}


def test_select_rows_with_sub_stratum_filter(tmp_path: Path) -> None:
    manifest = _build_one_cell_manifest(tmp_path)
    rows = select_rows(manifest, stratum="supplementary", sub_stratum="named_audit")
    assert len(rows) == 5


def test_partial_assemble_returns_dict(tmp_path: Path) -> None:
    """When we call assemble_manifest with a partial base set the
    expected-count check should fire (since the partial run has fewer
    than 285 main variants).
    """
    cell = cell_by_index(0)
    base_records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    expand_base_records_to_variants(base_records=base_records, base_dir=tmp_path)
    with pytest.raises(ValueError) as excinfo:
        assemble_manifest(out_dir=tmp_path, base_records=base_records)
    assert "main variants" in str(excinfo.value)


def test_total_constants_align() -> None:
    assert (
        EXPECTED_MAIN_VARIANTS + EXPECTED_SUPPLEMENTARY_VARIANTS
        == EXPECTED_TOTAL_VARIANTS
    )
    # v2 with MARBLE bargaining seed expansion, two bidding cells, and
    # two travel cells: 465 main + 50 supplementary = 515.
    assert EXPECTED_TOTAL_VARIANTS == 515


def test_assemble_manifest_force_rebuilds_variant_index(tmp_path: Path) -> None:
    """Codex Batch S3 non-blocker: ``assemble_manifest`` must not reuse
    a stale ``phase5_variants_index.json`` when called with new
    ``base_records``. The previous behavior returned the full expected rows
    even after rerunning with a single cell, which masked stale data.
    """
    cell_a = cell_by_index(0)  # CD-A-marble_research (8 tasks)
    full_base = generate_base_bundles(out_dir=tmp_path, cells=(cell_a,))
    expand_base_records_to_variants(base_records=full_base, base_dir=tmp_path)
    # Now call assemble_manifest with a *smaller* set than what was
    # written to disk. The default (force-rebuild) path should bring
    # the manifest back in sync with the new input.
    partial_base = full_base[:3]
    with pytest.raises(ValueError):
        # We still get the expected-count check on partial main rows.
        assemble_manifest(out_dir=tmp_path, base_records=partial_base)
    # The variant index was rebuilt to match the partial set even
    # though the manifest's count check raised.
    from clawsocialarena.generator.phase5_attack_variants import (
        PHASE5_VARIANT_INDEX_FILENAME,
        load_variant_index,
    )

    rebuilt = load_variant_index(tmp_path / PHASE5_VARIANT_INDEX_FILENAME)
    assert len(rebuilt) == len(partial_base) * 5


@pytest.mark.slow
def test_full_manifest_writes_515_rows(tmp_path: Path) -> None:
    """End-to-end materialization across all 18 cells. Marked slow so
    the default `pytest -q` run skips it via `-m 'not slow'`. v2 math
    (MARBLE bargaining, bidding, and travel expanded):
      3 × 8 × 5 = 120 (marble_research)
      2 × 12 × 5 = 120 (marble_bargaining)
      2 × 6 × 5 = 60 (marble_bidding)
      11 × 3 × 5 = 165 (other families)
      Total: 465 main + 50 supplementary = 515.
    """
    manifest = _build_full_manifest(tmp_path)
    assert manifest["n_main"] == EXPECTED_MAIN_VARIANTS
    assert manifest["n_supplementary"] == EXPECTED_SUPPLEMENTARY_VARIANTS
    assert manifest["n_total"] == EXPECTED_TOTAL_VARIANTS
    on_disk = load_manifest(tmp_path / PHASE5_MANIFEST_FILENAME)
    assert on_disk["n_total"] == 515
    # Smoke: task_index=0 exists in all 18 cells -> 18 x 5 = 90 rows.
    smoke = select_rows(on_disk, stratum="main", task_index=0)
    assert len(smoke) == 90
    # Per-mode totals: 93 base bundles x 5 modes / 5 = 93 per mode.
    for mode in ("no_attacker", "collaboration", "security", "privacy", "governance"):
        assert len(select_rows(on_disk, stratum="main", attack_mode=mode)) == 93
