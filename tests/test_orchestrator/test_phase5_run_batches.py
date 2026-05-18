"""Tests for the Phase-5 run-batch slicing (S4 step 1, T12 redesign)."""
from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.generator.phase5_attack_variants import (
    expand_base_records_to_variants,
)
from clawsocialarena.generator.phase5_base_generator import (
    generate_base_bundles,
)
from clawsocialarena.generator.phase5_manifest import assemble_manifest
from clawsocialarena.orchestrator.phase5_run_batches import (
    PHASE5_RUN_BATCHES,
    run_batch_for,
    total_expected_rows,
)


def test_batch_numbers_are_one_through_five() -> None:
    assert [s.batch_number for s in PHASE5_RUN_BATCHES] == [1, 2, 3, 4, 5]


def test_batch_names_are_attack_regime_based() -> None:
    names = [s.name for s in PHASE5_RUN_BATCHES]
    assert names == ["smoke_v2", "standard", "stress", "cross_model", "supplementary"]


def test_run_batch_for_returns_spec_or_raises() -> None:
    spec = run_batch_for(1)
    assert spec.name == "smoke_v2"
    with pytest.raises(ValueError):
        run_batch_for(99)


def test_total_expected_rows_reflects_overlap() -> None:
    """R-B 2 and R-B 4 share the same row set; total is not unique pilot rows."""
    total = total_expected_rows()
    # 40 + 465 + 372 + 465 + 50 = 1392
    assert total == sum(s.expected_rows for s in PHASE5_RUN_BATCHES)


@pytest.fixture(scope="module")
def full_manifest(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """One full 465-row main + 50-row supplementary manifest reused across tests."""
    out_dir = tmp_path_factory.mktemp("phase5_full_manifest")
    base_records = generate_base_bundles(out_dir=out_dir)
    expand_base_records_to_variants(
        base_records=base_records, base_dir=out_dir
    )
    return assemble_manifest(out_dir=out_dir, base_records=base_records)


def test_each_batch_selector_lands_expected_row_count(full_manifest) -> None:
    """Every batch's selector must return a count in its declared valid set."""
    for spec in PHASE5_RUN_BATCHES:
        rows = spec.select(full_manifest)
        valid = {spec.expected_rows, *spec.expected_rows_alternatives}
        assert len(rows) in valid, (
            f"batch {spec.batch_number} ({spec.name}) returned "
            f"{len(rows)} rows, expected one of {sorted(valid)}"
        )


def test_batch_1_smoke_covers_every_attack_mode(full_manifest) -> None:
    """The smoke batch must include all 5 attack modes so attacker issues
    surface even at the smallest run.
    """
    spec = run_batch_for(1)
    rows = spec.select(full_manifest)
    modes = {row["attack_mode"] for row in rows}
    assert modes == {
        "no_attacker",
        "collaboration",
        "security",
        "privacy",
        "governance",
    }


def test_batch_1_smoke_one_row_per_family_mode(full_manifest) -> None:
    """Smoke must have exactly one row per (family_id, attack_mode) combination."""
    spec = run_batch_for(1)
    rows = spec.select(full_manifest)
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["family_id"], row["attack_mode"])
        assert key not in seen, f"duplicate (family, mode) pair: {key}"
        seen.add(key)


def test_batch_2_standard_is_all_main_rows(full_manifest) -> None:
    spec = run_batch_for(2)
    rows = spec.select(full_manifest)
    assert {row["stratum"] for row in rows} == {"main"}
    assert len(rows) == len(full_manifest["main"])


def test_batch_3_stress_excludes_baseline(full_manifest) -> None:
    spec = run_batch_for(3)
    rows = spec.select(full_manifest)
    assert all(row["attack_mode"] != "no_attacker" for row in rows)


def test_batch_4_cross_model_matches_standard(full_manifest) -> None:
    standard_rows = run_batch_for(2).select(full_manifest)
    cross_rows = run_batch_for(4).select(full_manifest)
    assert [r["variant_id"] for r in cross_rows] == [
        r["variant_id"] for r in standard_rows
    ]


def test_batch_5_is_only_supplementary(full_manifest) -> None:
    spec = run_batch_for(5)
    rows = spec.select(full_manifest)
    assert {row["stratum"] for row in rows} == {"supplementary"}
    sub_strata = {row["sub_stratum"] for row in rows}
    assert sub_strata == {"hard_verification", "episode_graph", "named_audit"}


def test_select_raises_on_count_mismatch(full_manifest) -> None:
    """If the manifest schema drifts beyond all expected alternatives, each
    spec must catch the drift loudly rather than silently under-running.
    """
    truncated = {
        **full_manifest,
        "main": full_manifest["main"][:1],
    }
    with pytest.raises(ValueError) as excinfo:
        run_batch_for(1).select(truncated)
    assert "expected" in str(excinfo.value)
