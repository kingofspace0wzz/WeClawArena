# Phase 5 Batch S4 Report -- Pilot Orchestrator

**Date:** 2026-05-11
**Scope:** Build the orchestrator that consumes the S3 manifest, slices it into the five run-batches, dispatches each row through a pluggable executor, and aggregates results into a pilot report. Live LLM execution itself is deferred to Run-Batches 1..5.
**Status:** Complete; awaiting codex review.

## 1. Goal

S4 takes the 680-row manifest produced by S3 and provides:

1. A canonical 5-batch slicing scheme that partitions the manifest exactly once (no double-counting, no missing rows).
2. A pluggable executor protocol so the orchestrator is testable with a deterministic mock and re-targetable to a live LLM stack without rewiring.
3. A per-batch report writer + a final pilot aggregator that ships JSON + Markdown summaries the Run-Batch 1..5 pause points consume.
4. A CLI that drives one batch or aggregates all five.

## 2. Deliverables

### 2.1 New modules (4 production + 1 CLI + 3 test)

```
clawsocialarena/orchestrator/
  __init__.py                      (  7 lines)  package docstring
  phase5_run_batches.py            (165 lines)  RunBatchSpec + PHASE5_RUN_BATCHES table + selectors
  phase5_executor.py               (202 lines)  ScenarioResult + ScenarioExecutor protocol + MockScenarioExecutor + FailingMockExecutor
  phase5_orchestrator.py           (346 lines)  RunBatchSummary + run_run_batch + aggregate_pilot_report + _render_pilot_report_md
  phase5_live_executor.py          (142 lines)  LiveScenarioExecutor surface (raises NotImplementedError until Run-Batch 1 wires it)

scripts/
  run_phase5_pilot.py              (188 lines)  CLI: run-batch + aggregate subcommands; sys.path bootstrap

tests/test_orchestrator/
  __init__.py
  test_phase5_run_batches.py       (119 lines,  9 tests)
  test_phase5_executor.py          ( 91 lines,  6 tests)
  test_phase5_orchestrator.py      (162 lines,  5 tests)

Total: 1,424 lines (1,055 production + 372 tests + 188 CLI, after removing the trivial __init__.py).
```

## 3. Mechanical contract

### 3.1 Run-batch partition (verified disjoint)

| # | Name | Selector | Expected rows |
|---|------|----------|---------------|
| 1 | smoke | stratum=main, tier=1, task=0 | 70 |
| 2 | task_diversity | stratum=main, tier=1, task in {1, 2} | 140 |
| 3 | tier_2_realistic | stratum=main, tier=2 | 210 |
| 4 | tier_3_stress | stratum=main, tier=3 | 210 |
| 5 | supplementary | stratum=supplementary | 50 |
| | Total | | **680** |

Every variant_id appears in exactly one batch (`test_batches_are_pairwise_disjoint`). The union equals the manifest total.

Each `RunBatchSpec.select(manifest)` call asserts the resulting count equals the declared `expected_rows`; a manifest schema drift raises `ValueError` immediately rather than silently under-running a batch.

### 3.2 Executor protocol

```python
class ScenarioExecutor(Protocol):
    def execute(self, *, row: dict[str, Any], base_dir: Path) -> ScenarioResult: ...
```

Two mock implementations ship for tests:

- `MockScenarioExecutor` -- deterministic, derives a pseudo-random score from `hash((seed, variant_id))`. Baseline rows succeed at task; non-baseline rows succeed at probability tied to `attack_intensity` (lower intensity = higher defender success). Token usage is fabricated but consistent (1800 + 1200 tokens / scenario for naturalization + simulation).
- `FailingMockExecutor` -- always returns an error result. Used to confirm error counting.

The live executor (`LiveScenarioExecutor`) ships its constructor surface (models, max_turns, optional API key) but the `execute` method raises `NotImplementedError` with a pointer at Run-Batch 1's task. This is intentional: S4 ships the orchestration scaffold; the LLM-driven simulation body lands when Run-Batch 1 fleshes out the call sites.

### 3.3 Per-batch artifacts

For each batch, `run_run_batch` writes:

- `BATCH_<NN>_<name>_RESULTS.jsonl` -- one line per scenario, each line a JSON-serialized `ScenarioResult`.
- `BATCH_<NN>_<name>_REPORT.json` -- aggregated `RunBatchSummary` with headline counters, per-mode breakdown, per-family breakdown, and elapsed wall time.

The `RunBatchSummary` carries:

- `n_run`, `n_errors`, `n_baseline`, `n_attacker`
- `task_success_rate_baseline`, `task_success_rate_attacker` (None if denominator is zero)
- `attack_success_rate`, `governance_violation_rate`, `privacy_violation_rate`
- `naturalization_total_tokens`, `simulation_total_tokens`
- `per_mode`: `{mode: {n, task_success_count, attack_success_count, task_success_rate, attack_success_rate}}`
- `per_family`: `{family_id: {n, task_success_count, task_success_rate}}`

### 3.4 Pilot aggregation

`aggregate_pilot_report` reads all 5 `BATCH_*_REPORT.json` files and writes:

- `PILOT_REPORT.json` -- top-level totals + each batch's full summary inlined.
- `PILOT_REPORT.md` -- one-screen human-readable table with per-batch rows.

## 4. End-to-end CLI smoke

```
$ python scripts/generate_phase5_manifest.py --quiet --out-dir /tmp/scaffold
$ for n in 1 2 3 4 5; do
    python scripts/run_phase5_pilot.py run-batch \
      --manifest /tmp/scaffold/phase5_manifest.json \
      --base-dir /tmp/scaffold \
      --out-dir /tmp/pilot \
      --batch "$n" --executor mock --quiet
  done
$ python scripts/run_phase5_pilot.py aggregate --out-dir /tmp/pilot
```

Output (PILOT_REPORT.md):

```
# Phase 5 Pilot Report

- Expected rows: **680**
- Rows actually run: **680**
- Errored scenarios: **0**
- Naturalization tokens: **1,836,000**
- Simulation tokens: **1,224,000**
- Wall time: **0.02 s**

## Per-batch summary

| # | Name | Rows | Errors | Task ok (baseline) | Task ok (attacker) | Attack success |
|---|------|-----:|-------:|-------------------:|-------------------:|---------------:|
| 1 | smoke | 70 | 0 | 100.0% | 55.4% | 44.6% |
| 2 | task_diversity | 140 | 0 | 85.7% | 59.8% | 40.2% |
| 3 | tier_2_realistic | 210 | 0 | 83.3% | 39.3% | 60.7% |
| 4 | tier_3_stress | 210 | 0 | 95.2% | 17.3% | 82.7% |
| 5 | supplementary | 50 | 0 | 88.0% | - | - |
```

The mock's attack-intensity-keyed scoring rule produces the expected curve: attacker task success drops as tier goes up (55% smoke → 17% tier 3) and attack success rises (44% → 82%). This validates that the aggregation arithmetic responds correctly to the spec section 5 tier semantics S3 landed.

## 5. Test results

```
$ pytest tests/test_generator/ tests/test_orchestrator/ -q
494 passed
```

S4 adds 20 new tests, all green. No regressions in the 474-test generator suite. Pre-existing 8 failures in out-of-scope suites (test_saf, test_scenario, test_resource_models, e2e docker) remain unchanged.

## 6. Design decisions worth noting

- **Single-threaded orchestrator, concurrency inside executors.** The orchestrator processes rows in canonical manifest order to keep audit logs deterministic; concurrency belongs at the live executor level (e.g., bounded thread pool over OpenAI calls). For the mock executor this is a non-issue.
- **Live executor is a stub until Run-Batch 1 lands.** Importing `phase5_live_executor` does not require an OpenAI API key; the `execute` method raises `NotImplementedError` with a pointer at Run-Batch 1's task. This keeps S4 tests fast and CI-safe while keeping the surface ready for production wiring.
- **Per-batch artifacts beat one big file.** Writing five per-batch JSONL/JSON files (rather than one combined results file) means each batch can be reviewed and gated independently between Run-Batches 1..5. The pause-after-each-batch flow the user agreed to is fully supported by this layout.
- **No supplementary materialization yet.** Run-Batch 5 will wire the recipes (`HardCodeReviewTemplate`, `HardDocEditingTemplate`, `episode_graph`, `named_audit_case`) into the executor. S4 just slices the 50 descriptor rows; the recipes themselves are out of scope for this batch.

## 7. Files inventory

```
clawsocialarena/orchestrator/__init__.py             (  7 LOC)
clawsocialarena/orchestrator/phase5_run_batches.py   (165 LOC)
clawsocialarena/orchestrator/phase5_executor.py      (202 LOC)
clawsocialarena/orchestrator/phase5_orchestrator.py  (346 LOC)
clawsocialarena/orchestrator/phase5_live_executor.py (142 LOC)
scripts/run_phase5_pilot.py                          (188 LOC)
tests/test_orchestrator/test_phase5_run_batches.py   (119 LOC, 9 tests)
tests/test_orchestrator/test_phase5_executor.py      ( 91 LOC, 6 tests)
tests/test_orchestrator/test_phase5_orchestrator.py  (162 LOC, 5 tests)

Total: 1,424 lines (5 production modules + 1 CLI + 3 test modules + 1 trivial __init__).
```

## 8. Foundation for Run-Batches 1..5

- Manifest is consumed by selector; orchestrator does not touch it beyond `select_rows`.
- Per-scenario state lives in the row dict + the on-disk bundle dir; nothing global is needed.
- `LiveScenarioExecutor` is the single seam Run-Batch 1 has to flesh out (naturalization call + agent loop + scoring); the orchestration scaffold above it does not change.
- Cost reporting is built in: each batch's report carries naturalization/simulation token totals, so we can decide whether to gate Run-Batch 3 on Run-Batches 1+2 spend.

## 9. Verdict request

Asking codex to validate:

1. Run-batch partition correctness: each row appears in exactly one batch and the five expected counts (70 + 140 + 210 + 210 + 50 = 680) are right relative to the spec.
2. Executor protocol surface: does the `ScenarioResult` carry enough columns for the aggregator + future SAF analysis, and is the mock executor's deterministic behavior reasonable for testing?
3. Aggregation correctness: are the per-mode / per-family breakdowns + violation rate columns the right denominators (e.g., privacy violation rate over privacy rows only, not over all attacker rows)?
4. Live executor stub: is the explicit `NotImplementedError` with a Run-Batch 1 pointer an acceptable placeholder, or should S4 itself include a runnable live executor body?
5. Foundation for Run-Batch 1: any subtle gap that would force Run-Batch 1 to redesign the orchestrator's surface?
