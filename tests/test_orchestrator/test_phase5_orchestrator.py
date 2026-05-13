"""Tests for the Phase-5 orchestrator entry points (S4 step 3)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawsocialarena.generator.phase5_attack_variants import (
    expand_base_records_to_variants,
)
from clawsocialarena.generator.phase5_base_generator import (
    generate_base_bundles,
)
from clawsocialarena.generator.phase5_manifest import assemble_manifest
from clawsocialarena.orchestrator.phase5_executor import (
    FailingMockExecutor,
    MockScenarioExecutor,
)
from clawsocialarena.orchestrator.phase5_orchestrator import (
    PHASE5_BATCH_REPORT_FILENAME_TEMPLATE,
    PHASE5_BATCH_RESULTS_FILENAME_TEMPLATE,
    PHASE5_PILOT_REPORT_JSON,
    PHASE5_PILOT_REPORT_MD,
    PHASE5_RUN_BATCHES,
    aggregate_pilot_report,
    run_run_batch,
)


@pytest.fixture(scope="module")
def shared_manifest(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    """One full 680-row manifest reused across orchestrator tests."""
    out_dir = tmp_path_factory.mktemp("phase5_orch_manifest")
    base_records = generate_base_bundles(out_dir=out_dir)
    expand_base_records_to_variants(
        base_records=base_records, base_dir=out_dir
    )
    manifest = assemble_manifest(out_dir=out_dir, base_records=base_records)
    return out_dir, manifest


def test_run_batch_writes_results_jsonl_and_report_json(
    shared_manifest, tmp_path: Path
) -> None:
    base_dir, manifest = shared_manifest
    executor = MockScenarioExecutor(seed=1)
    summary, results = run_run_batch(
        manifest=manifest,
        batch_number=1,
        executor=executor,
        base_dir=base_dir,
        out_dir=tmp_path,
    )
    # Batch 1 is smoke_v2: one row per (family, mode) = 30 rows at spec-1 scale.
    assert summary.n_run == 30 == len(results)
    assert summary.n_errors == 0
    # The two per-batch artifacts are written.
    results_path = tmp_path / PHASE5_BATCH_RESULTS_FILENAME_TEMPLATE.format(
        batch=1, name="smoke_v2"
    )
    report_path = tmp_path / PHASE5_BATCH_REPORT_FILENAME_TEMPLATE.format(
        batch=1, name="smoke_v2"
    )
    assert results_path.is_file() and report_path.is_file()
    # The JSONL has one row per scenario.
    with results_path.open(encoding="utf-8") as fh:
        lines = [line for line in fh if line.strip()]
    assert len(lines) == 30
    # Every line is valid JSON.
    for line in lines:
        json.loads(line)


def test_summary_rate_fields_are_present_and_well_formed(
    shared_manifest, tmp_path: Path
) -> None:
    base_dir, manifest = shared_manifest
    executor = MockScenarioExecutor(seed=42)
    summary, _ = run_run_batch(
        manifest=manifest,
        batch_number=1,
        executor=executor,
        base_dir=base_dir,
        out_dir=tmp_path,
    )
    # Per-mode breakdown should include every attack_mode.
    assert set(summary.per_mode.keys()) == {
        "no_attacker",
        "collaboration",
        "security",
        "privacy",
        "governance",
    }
    # The five per-mode rows sum to the batch total (30 at spec-1 scale).
    assert sum(bucket["n"] for bucket in summary.per_mode.values()) == 30
    # Per-family breakdown spans every registered family that has a cell.
    assert summary.per_family, "per_family is empty"


def test_failing_executor_counts_errors_separately(
    shared_manifest, tmp_path: Path
) -> None:
    """Errored rows must drop out of every rate denominator (codex S4
    blocker): if all 70 rows error, every rate must be ``None``, not
    ``0.0``. The previous implementation divided by the raw row
    count and silently misreported readiness failures as measured
    outcomes.
    """
    base_dir, manifest = shared_manifest
    executor = FailingMockExecutor()
    summary, results = run_run_batch(
        manifest=manifest,
        batch_number=1,
        executor=executor,
        base_dir=base_dir,
        out_dir=tmp_path,
    )
    # Batch 1 is smoke_v2: 30 rows at spec-1 scale.
    assert summary.n_run == 30
    assert summary.n_errors == 30
    assert summary.task_success_count == 0
    assert summary.attack_success_count == 0
    # Every rate must be None because no row contributed a definite outcome.
    assert summary.task_success_rate_baseline is None
    assert summary.task_success_rate_attacker is None
    assert summary.attack_success_rate is None
    assert summary.governance_violation_rate is None
    assert summary.privacy_violation_rate is None
    assert all(r.error == FailingMockExecutor().error_message for r in results)


def test_raising_executor_is_caught_per_row(
    shared_manifest, tmp_path: Path
) -> None:
    """A live executor that throws must not abort the batch. The
    orchestrator should record a synthetic error result for the bad
    row and continue with the rest.
    """
    base_dir, manifest = shared_manifest

    class _SometimesRaisesExecutor:
        """Throws on every third row; returns a normal mock result otherwise."""

        def __init__(self) -> None:
            self._counter = 0
            self._mock = MockScenarioExecutor()

        def execute(self, *, row, base_dir):
            self._counter += 1
            if self._counter % 3 == 0:
                raise RuntimeError("simulated executor failure")
            return self._mock.execute(row=row, base_dir=base_dir)

    summary, results = run_run_batch(
        manifest=manifest,
        batch_number=1,
        executor=_SometimesRaisesExecutor(),
        base_dir=base_dir,
        out_dir=tmp_path,
    )
    # The batch ran to completion (all 30 rows accounted for) instead
    # of aborting on the first raise. Batch 1 is smoke_v2 at spec-1 scale.
    assert summary.n_run == 30
    # Roughly a third of the rows errored.
    expected_errors = 30 // 3
    assert summary.n_errors == expected_errors
    # Errored rows carry the raised exception's repr.
    errored = [r for r in results if r.error is not None]
    assert errored, "no errored rows captured"
    assert all("simulated executor failure" in r.error for r in errored)


def test_mock_executor_is_process_stable(
    shared_manifest, tmp_path: Path
) -> None:
    """Codex S4 blocker: the mock's deterministic_score must not depend
    on Python's salted ``hash()``. Two fresh orchestrator runs against
    the same manifest + seed must produce identical per-batch summary
    counts. We exercise this by invoking Python in a subshell with a
    fresh PYTHONHASHSEED and comparing the JSON-serialized summaries.
    """
    import os
    import subprocess
    import sys

    base_dir, manifest = shared_manifest
    # Persist the manifest for the subprocess.
    manifest_path = tmp_path / "shared_manifest.json"
    import json as _json

    manifest_path.write_text(_json.dumps(manifest), encoding="utf-8")

    helper = tmp_path / "run_smoke.py"
    helper.write_text(
        "import json, sys, pathlib\n"
        f"sys.path.insert(0, {str(_REPO_ROOT_FOR_TESTS())!r})\n"
        "from clawsocialarena.orchestrator.phase5_executor import MockScenarioExecutor\n"
        "from clawsocialarena.orchestrator.phase5_orchestrator import run_run_batch\n"
        f"manifest = json.loads(pathlib.Path({str(manifest_path)!r}).read_text())\n"
        "summary, _ = run_run_batch(\n"
        "    manifest=manifest, batch_number=1,\n"
        "    executor=MockScenarioExecutor(seed=99),\n"
        f"    base_dir={str(base_dir)!r}, out_dir={str(tmp_path / 'out1')!r},\n"
        ")\n"
        "print(json.dumps({\n"
        "    'task_success_count': summary.task_success_count,\n"
        "    'attack_success_count': summary.attack_success_count,\n"
        "    'per_mode': summary.per_mode,\n"
        "}, sort_keys=True))\n"
    )
    env_a = {**os.environ, "PYTHONHASHSEED": "1"}
    env_b = {**os.environ, "PYTHONHASHSEED": "999"}
    out_a = subprocess.check_output(
        [sys.executable, str(helper)], env=env_a, text=True
    )
    out_b = subprocess.check_output(
        [sys.executable, str(helper)], env=env_b, text=True
    )
    assert out_a == out_b, (
        "MockScenarioExecutor results differ across PYTHONHASHSEED; "
        "use a stable hash (e.g., zlib.crc32) instead of Python's "
        "built-in hash()."
    )


def _REPO_ROOT_FOR_TESTS() -> str:
    """The repo root, so the subprocess helper can import clawsocialarena."""
    return str(Path(__file__).resolve().parent.parent.parent)


def test_attacker_modes_only_contribute_to_violation_columns(
    shared_manifest, tmp_path: Path
) -> None:
    base_dir, manifest = shared_manifest
    executor = MockScenarioExecutor(seed=7)
    summary, _ = run_run_batch(
        manifest=manifest,
        batch_number=1,
        executor=executor,
        base_dir=base_dir,
        out_dir=tmp_path,
    )
    # The baseline mode never reports a governance / privacy violation.
    baseline = summary.per_mode["no_attacker"]
    assert baseline["attack_success_rate"] is None


def test_aggregate_combines_all_five_batches(
    shared_manifest, tmp_path: Path
) -> None:
    base_dir, manifest = shared_manifest
    executor = MockScenarioExecutor(seed=11)
    summaries = []
    for spec in PHASE5_RUN_BATCHES:
        summary, _ = run_run_batch(
            manifest=manifest,
            batch_number=spec.batch_number,
            executor=executor,
            base_dir=base_dir,
            out_dir=tmp_path,
        )
        summaries.append(summary)
    payload = aggregate_pilot_report(out_dir=tmp_path, batch_summaries=summaries)
    # Attack-regime-based batches (T12): 30+210+168+210+50 = 668.
    # R-B 2 (standard) and R-B 4 (cross_model) share the same 210 main rows,
    # so the sum overestimates unique pilot rows but each batch runs independently.
    from clawsocialarena.orchestrator.phase5_run_batches import total_expected_rows
    expected = total_expected_rows()
    assert payload["expected_total_rows"] == expected
    assert payload["total_rows_run"] == expected
    assert payload["total_errors"] == 0
    json_path = tmp_path / PHASE5_PILOT_REPORT_JSON
    md_path = tmp_path / PHASE5_PILOT_REPORT_MD
    assert json_path.is_file() and md_path.is_file()
    md = md_path.read_text(encoding="utf-8")
    # The markdown header and a row per batch should be present.
    assert "Phase 5 Pilot Report" in md
    for spec in PHASE5_RUN_BATCHES:
        assert spec.name in md
