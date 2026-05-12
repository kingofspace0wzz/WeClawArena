"""Tests for the Phase-5 run-batch slicing (S4 step 1)."""
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


def test_expected_row_counts_sum_to_pilot_total() -> None:
    """The 5 batch row counts must sum to the 680-row pilot manifest."""
    assert total_expected_rows() == 680
    assert [s.expected_rows for s in PHASE5_RUN_BATCHES] == [70, 140, 210, 210, 50]


def test_batch_numbers_are_one_through_five() -> None:
    assert [s.batch_number for s in PHASE5_RUN_BATCHES] == [1, 2, 3, 4, 5]


def test_run_batch_for_returns_spec_or_raises() -> None:
    spec = run_batch_for(1)
    assert spec.name == "smoke"
    with pytest.raises(ValueError):
        run_batch_for(99)


@pytest.fixture(scope="module")
def full_manifest(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """One full 680-row manifest reused across the slicing tests."""
    out_dir = tmp_path_factory.mktemp("phase5_full_manifest")
    base_records = generate_base_bundles(out_dir=out_dir)
    expand_base_records_to_variants(
        base_records=base_records, base_dir=out_dir
    )
    return assemble_manifest(out_dir=out_dir, base_records=base_records)


def test_each_batch_selector_lands_expected_row_count(full_manifest) -> None:
    """Every batch's selector must produce exactly its declared count."""
    for spec in PHASE5_RUN_BATCHES:
        rows = spec.select(full_manifest)
        assert len(rows) == spec.expected_rows, (
            f"batch {spec.batch_number} ({spec.name}) returned "
            f"{len(rows)} rows, expected {spec.expected_rows}"
        )


def test_batches_are_pairwise_disjoint(full_manifest) -> None:
    """No variant_id may appear in more than one batch; if it did the
    pilot would double-count that row.
    """
    seen: dict[str, int] = {}
    for spec in PHASE5_RUN_BATCHES:
        for row in spec.select(full_manifest):
            vid = row["variant_id"]
            assert vid not in seen, (
                f"variant_id {vid} appears in batches {seen[vid]} and "
                f"{spec.batch_number}"
            )
            seen[vid] = spec.batch_number
    # And the union must equal the full manifest count.
    assert len(seen) == 680


def test_batch_1_smoke_covers_every_attack_mode(full_manifest) -> None:
    """The 70-row smoke must include all 5 attack modes so attacker
    issues surface even at the smallest run.
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


def test_batch_3_and_4_partition_tiers_2_and_3(full_manifest) -> None:
    tier_2 = run_batch_for(3).select(full_manifest)
    tier_3 = run_batch_for(4).select(full_manifest)
    assert {row["tier_index"] for row in tier_2} == {2}
    assert {row["tier_index"] for row in tier_3} == {3}


def test_batch_5_is_only_supplementary(full_manifest) -> None:
    spec = run_batch_for(5)
    rows = spec.select(full_manifest)
    assert {row["stratum"] for row in rows} == {"supplementary"}
    sub_strata = {row["sub_stratum"] for row in rows}
    assert sub_strata == {"hard_verification", "episode_graph", "named_audit"}


def test_select_raises_on_count_mismatch(full_manifest) -> None:
    """If the manifest schema drifts (e.g., main is partial), each
    spec must catch the count drift loudly rather than silently
    under-running.
    """
    truncated = {
        **full_manifest,
        "main": full_manifest["main"][:5],
    }
    with pytest.raises(ValueError) as excinfo:
        run_batch_for(1).select(truncated)
    assert "expected" in str(excinfo.value)
