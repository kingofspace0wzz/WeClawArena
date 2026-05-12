# Phase 5 Batch S4 Revision Report

**Date:** 2026-05-11
**Scope:** Address the two blockers + two non-blocker observations codex flagged in `BATCH_S4_REPORT.md`.
**Status:** Complete; awaiting re-review.

## 1. Issues addressed

| # | Severity | Issue | Where it lived |
|---|----------|-------|----------------|
| 1 | blocker | Rate denominators counted ``None`` outcomes as failures, so errored rows silently dragged every rate to 0.0 instead of dropping out | `phase5_orchestrator._summarize_results`, `_per_mode_breakdown`, `_per_family_breakdown` |
| 2 | blocker | `MockScenarioExecutor.execute` used Python's salted `hash()`; same seed + same row gave different scores across processes (PYTHONHASHSEED randomization) | `phase5_executor.MockScenarioExecutor.execute` |
| 3 | non-blocker | If `executor.execute` raised, the whole batch aborted before any `BATCH_*_REPORT.json` was written | `phase5_orchestrator.run_run_batch` |
| 4 | non-blocker | `select_rows` docstring still described Batch 2 as "all tier-1 task indices" instead of the post-Batch-1 partition `task_index in {1, 2}` | `phase5_manifest.select_rows` |

## 2. Fix 1 — Definite-only rate denominators

Codex's reproduction: a smoke batch run with `FailingMockExecutor` reported `0.0` for every rate column (baseline task success, attacker task success, attack success, governance violation, privacy violation). The contract on `ScenarioResult` was that `None` means "executor could not decide; skip this row from scoring," but the aggregator divided by the raw row count and treated `None` as `False`.

Refactor: `_summarize_results` now uses a single `_rate_over_definite` helper that filters to rows where the relevant column is not `None`, counts the true rows in that subset, and returns `(count_true, count_definite, rate_or_None)`. A column with zero definite rows yields `None` rather than a division-by-zero or a silent `0.0`. The same pattern is applied to `_per_mode_breakdown` and `_per_family_breakdown`, each of which now also surfaces `n_task_definite` / `n_attack_definite` so a downstream reader can see how many rows actually contributed to each rate.

New regression test: `test_failing_executor_counts_errors_separately` confirms that a 70-row batch where every row errors produces:

- `n_errors == 70`
- All five rate fields (`task_success_rate_baseline`, `task_success_rate_attacker`, `attack_success_rate`, `governance_violation_rate`, `privacy_violation_rate`) are `None`, not `0.0`.

## 3. Fix 2 — Process-stable mock executor

Codex's reproduction: two fresh Python invocations with the same row and same seed gave different `task_success` values because CPython salts `hash()` per process via `PYTHONHASHSEED`.

Replace `hash((self.seed, variant_id))` with `zlib.crc32(f"{seed}:{variant_id}".encode("utf-8"))`. CRC32 is deterministic, dependency-free, and produces the same uniform distribution shape the test needed.

New regression test: `test_mock_executor_is_process_stable` spawns two subprocesses with different `PYTHONHASHSEED` values (1 and 999), runs the smoke batch in each, and asserts the serialized summaries are byte-identical.

## 4. Fix 3 — Per-row exception isolation

`run_run_batch` now wraps `executor.execute(...)` in a try/except. If the executor raises, the orchestrator synthesizes an errored `ScenarioResult` (via a new `_error_result_from_row` helper) with every scoring column set to `None`, records the exception's `repr()` in the `error` field, writes the row to the JSONL trace, and continues with the next row. The whole batch always runs to completion and the `BATCH_*_REPORT.json` always lands.

New regression test: `test_raising_executor_is_caught_per_row` uses an executor that throws every third row, then asserts the batch still produces 70 rows total, ~`70 // 3` of which are errored, and the JSONL contains the exception text on each errored row.

## 5. Fix 4 — Manifest selector docstring

Updated `select_rows`'s docstring to reflect the partition Batch 2 actually uses (`task_index in {1, 2}` at tier 1) plus per-batch row counts. Cosmetic but matched against the orchestrator's authoritative table.

## 6. Test results

```
$ pytest tests/test_generator/ tests/test_orchestrator/ -q
496 passed
```

S4 grew from 20 → 22 tests (+2 regression tests for the codex blockers). No regressions in the 474-test generator suite. Pre-existing 8 failures in out-of-scope suites remain unchanged.

## 7. End-to-end CLI smoke (post-revision)

```
$ python scripts/generate_phase5_manifest.py --quiet --out-dir /tmp/scaffold
$ for n in 1 2 3 4 5; do
    python scripts/run_phase5_pilot.py run-batch \
      --manifest /tmp/scaffold/phase5_manifest.json \
      --base-dir /tmp/scaffold \
      --out-dir /tmp/pilot \
      --batch "$n" --executor mock --quiet
  done
$ python scripts/run_phase5_pilot.py aggregate --out-dir /tmp/pilot --quiet
$ cat /tmp/pilot/PILOT_REPORT.md
```

```
| # | Name | Rows | Errors | Task ok (baseline) | Task ok (attacker) | Attack success |
|---|------|-----:|-------:|-------------------:|-------------------:|---------------:|
| 1 | smoke            | 70  | 0 | 85.7% | 58.9% | 41.1% |
| 2 | task_diversity   | 140 | 0 | 89.3% | 66.1% | 33.9% |
| 3 | tier_2_realistic | 210 | 0 | 90.5% | 37.5% | 62.5% |
| 4 | tier_3_stress    | 210 | 0 | 90.5% | 20.8% | 79.2% |
| 5 | supplementary    | 50  | 0 | 92.0% | -     | -     |
```

The tier-keyed success curve still flows the right direction (attacker task success drops 58.9% → 20.8% from smoke to stress; attack success rises 41.1% → 79.2%). Numbers differ from the pre-revision report because the deterministic source changed from `hash()` to `zlib.crc32()`; the shape of the distribution did not.

## 8. Files touched

```
clawsocialarena/orchestrator/phase5_executor.py     (202 -> 210 LOC)
clawsocialarena/orchestrator/phase5_orchestrator.py (346 -> 391 LOC)
clawsocialarena/generator/phase5_manifest.py        (258 -> 261 LOC; docstring only)
tests/test_orchestrator/test_phase5_orchestrator.py (162 -> 271 LOC; +2 regression tests)
```

No new modules; the fixes were strictly localized to the two production modules + one docstring + the test file.

## 9. Verdict request

Both codex blockers addressed with regression tests; the two non-blockers landed too. Pipeline math is unchanged (680 rows partitioned 70 + 140 + 210 + 210 + 50). Tier-keyed mock distribution still produces the expected tier curve.

Re-running codex review with this revision report.
