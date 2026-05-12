"""Concurrency contract tests for the Phase-5 orchestrator.

R-B 2 introduces a bounded :class:`ThreadPoolExecutor` so live
runs can overlap LLM calls. The orchestrator must preserve two
invariants regardless of completion order:

1. ``results[i]`` corresponds to ``manifest_rows[i]`` (canonical
   order).
2. The JSONL trace on disk also reflects canonical order, so an
   external watcher can diff runs by row index.

These tests use a deliberately-slow mock executor that randomizes
completion order via per-call sleep deltas, then asserts the
results land in canonical order anyway.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from clawsocialarena.generator.phase5_attack_variants import (
    expand_base_records_to_variants,
)
from clawsocialarena.generator.phase5_base_generator import (
    generate_base_bundles,
)
from clawsocialarena.generator.phase5_manifest import assemble_manifest
from clawsocialarena.orchestrator.phase5_executor import ScenarioResult
from clawsocialarena.orchestrator.phase5_orchestrator import run_run_batch


@dataclass
class _OrderShuffledExecutor:
    """Mock executor that sleeps a row-index-dependent amount so
    submission order != completion order. Records each row's
    variant_id with a synthetic ``task_success=True`` so the
    orchestrator's summarizer has data to work with.
    """

    sleep_pattern: list[float] = None  # type: ignore[assignment]
    _call_count: int = 0

    def execute(
        self,
        *,
        row: dict[str, Any],
        base_dir: Path,
    ) -> ScenarioResult:
        idx = self._call_count
        self._call_count += 1
        pattern = self.sleep_pattern or [0.05, 0.01, 0.04, 0.02, 0.03]
        time.sleep(pattern[idx % len(pattern)])
        return ScenarioResult(
            variant_id=row.get("variant_id", ""),
            base_scenario_id=row.get("base_scenario_id", ""),
            cell_id=row.get("cell_id", ""),
            family_id=row.get("family_id", ""),
            task_index=int(row.get("task_index", 0)),
            tier_index=int(row.get("tier_index", 0)),
            attack_mode=row.get("attack_mode", "no_attacker"),
            attack_recipe=row.get("attack_recipe"),
            naturalization_success=True,
            task_success=True,
            attack_success=None,
            governance_violation=None,
            privacy_violation=None,
            compliance_ok=True,
            turn_count=4,
            elapsed_seconds=0.05,
            extra={"shuffled_executor": True},
        )


@pytest.fixture(scope="module")
def smoke_manifest_and_base_dir(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[dict[str, Any], Path]:
    out_dir = tmp_path_factory.mktemp("phase5_concurrency_smoke")
    base_records = generate_base_bundles(out_dir=out_dir)
    expand_base_records_to_variants(
        base_records=base_records, base_dir=out_dir
    )
    manifest = assemble_manifest(out_dir=out_dir, base_records=base_records)
    return manifest, out_dir


def test_concurrent_run_preserves_canonical_row_order(
    smoke_manifest_and_base_dir, tmp_path: Path
) -> None:
    manifest, base_dir = smoke_manifest_and_base_dir
    executor = _OrderShuffledExecutor()
    summary, results = run_run_batch(
        manifest=manifest,
        batch_number=1,
        executor=executor,
        base_dir=base_dir,
        out_dir=tmp_path,
        max_workers=4,
    )
    # Compare results' variant_ids against the manifest's batch-1 rows.
    from clawsocialarena.orchestrator.phase5_run_batches import (
        run_batch_for,
    )
    spec = run_batch_for(1)
    expected_rows = spec.select(manifest)
    assert [r.variant_id for r in results] == [
        row["variant_id"] for row in expected_rows
    ]
    # The JSONL trace must mirror that order too.
    results_path = next(tmp_path.glob("BATCH_01_*_RESULTS.jsonl"))
    on_disk = [json.loads(line) for line in results_path.read_text().splitlines() if line]
    assert [r["variant_id"] for r in on_disk] == [
        row["variant_id"] for row in expected_rows
    ]
    assert summary.n_run == len(expected_rows)


def test_concurrency_max_workers_1_is_sequential(
    smoke_manifest_and_base_dir, tmp_path: Path
) -> None:
    """``max_workers=1`` is the deterministic fallback used by the
    test suite and by debugging runs. It must produce results in
    submission order (which equals canonical order, since the pool
    has only one worker).
    """
    manifest, base_dir = smoke_manifest_and_base_dir
    executor = _OrderShuffledExecutor(sleep_pattern=[0.0])
    _, results = run_run_batch(
        manifest=manifest,
        batch_number=1,
        executor=executor,
        base_dir=base_dir,
        out_dir=tmp_path,
        max_workers=1,
    )
    from clawsocialarena.orchestrator.phase5_run_batches import (
        run_batch_for,
    )
    spec = run_batch_for(1)
    expected_rows = spec.select(manifest)
    assert [r.variant_id for r in results] == [
        row["variant_id"] for row in expected_rows
    ]
