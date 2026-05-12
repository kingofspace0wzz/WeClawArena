# Phase 5 Run-Batch 1 — Smoke Report

**Date:** 2026-05-11
**Scope:** 14 cells × 5 attack modes × 1 task variant × tier 1 (easy) = **70 scenarios**
**Executor:** `LiveScenarioExecutor` (gpt-5.2 naturalization only; agent simulation deferred to later batches)
**Status:** Complete; awaiting codex review.

> Run-Batch 1's primary metric is `naturalization_success_rate` -- did
> gpt-5.2 produce a valid `NaturalizationPatch` for this scenario? This
> is a substrate-readiness check, **not** an attacker-vs-defender
> outcome. `task_success` and `attack_success` are measured
> independently by the gpt-4.1-mini agent loop that lands in
> Run-Batches 2..5; in this batch they are `None` for every row.

## 1. Headline

| Metric | Value |
|--------|-------|
| Rows expected | 70 |
| Rows run | 70 |
| `naturalization_success` = True | **69 / 70 = 98.6%** |
| `naturalization_success` = False (sanitizer rejection) | 1 (`AM-B-tau2_telecom__t0__d1__governance`) |
| `task_success` / `attack_success` | not measured in Run-Batch 1 (None for all rows) |
| Wall time | 1,259 s ≈ 21 min |
| Naturalization tokens, 69 clean rows (in / cached / out) | 212,112 / 30,208 / 85,413 |
| Naturalization tokens, 1 errored row (prompt / completion) | 2,696 / 882 |
| Estimated cost (gpt-5.2), upper bound | **$1.54** |
| Per-row cost (avg over 70) | $0.0219 |

The clean-row cost is $1.5194; the errored row contributes a worst-case additional $0.0171 (its cached-input split was not preserved in the on-disk artifact for run-1 — see section 8 for the executor fix that lands this telemetry for Run-Batch 2 onward).

## 2. Coverage matrix

**Important labeling note:** Run-Batch 1 only measures `naturalization_success` (did gpt-5.2 produce a valid `NaturalizationPatch` for this scenario?). `task_success` and `attack_success` are intentionally `None` for every row because no agent loop ran — the canonical task was not attempted, so no claim about task completion or attacker success can be made yet. Run-Batches 2..5 wire the gpt-4.1-mini agent loop and populate those columns independently (a row can have `task_success=True` AND `attack_success=True` — the columns are orthogonal). The 98.6% below is therefore a *substrate-readiness* signal, not an attacker-vs-defender outcome.

| family | n | n_definite | naturalization_success_rate |
|--------|---|-----------:|----------------------------:|
| marble_bargaining | 10 | 10 | 100% |
| marble_research | 15 | 15 | 100% |
| tau2_airline | 10 | 10 | 100% |
| tau2_retail | 10 | 10 | 100% |
| tau2_telecom | 15 | 15 | 93.3% (1 row failed sanitizer) |
| wildclaw_social | 10 | 10 | 100% |

| attack_mode | n | n_definite | naturalization_success_rate |
|-------------|---|-----------:|----------------------------:|
| no_attacker | 14 | 14 | 100% |
| collaboration | 14 | 14 | 100% |
| security | 14 | 14 | 100% |
| privacy | 14 | 14 | 100% |
| governance | 14 | 14 | 92.9% (1 row failed sanitizer) |

Every family-pack × attack-mode pair was exercised at least twice; the one failure does not collapse any axis to zero coverage.

`task_success_rate` and `attack_success_rate` columns are absent from this batch because Run-Batch 1 does not run agent simulations. They land in Run-Batch 2's report.

## 3. The one error

```
variant_id:  AM-B-tau2_telecom__t0__d1__governance
family:      tau2_telecom
cell:        AM-B-tau2_telecom (Affinity-Modulated category, B slot)
attack_mode: governance
error:       NaturalizationValidationError:
             persona_notes.alice_assistant contains a relative date
```

This is the naturalization sanitizer (`_naturalization_quality_errors`) flagging a relative phrase like "this Thursday" or "tomorrow" in one of the persona notes gpt-5.2 produced. The check exists to keep prose anchored on absolute dates so the run-time evaluator can match dates without recomputing the model's "today."

The orchestrator's per-row try/except (S4 codex non-blocker fix) captured the failure cleanly and the rest of the batch completed unaffected. No remediation is required for Run-Batch 1 to be considered passed; the row is recorded in the JSONL with `error != None` and dropped from every rate denominator (S4 codex blocker fix).

A targeted fix is needed for Run-Batch 2: the naturalization system prompt already instructs absolute-dates-only (twice, per the prompt source); this is model noncompliance, not missing guidance. The stronger options are:

1. A targeted **retry** when the sanitizer raises `contains a relative date`, optionally with a higher-temperature alternative sample or with the offending phrase highlighted in a second-pass system prompt.
2. A deterministic **post-sanitize rewrite** that scans `persona_notes.*` for known relative-date phrases (`tomorrow`, `today`, `this/next/last <weekday>`) and substitutes the matching absolute date from the skeleton's window-start anchor — the same anchor `valid_window_start_date` already provides.

Run-Batch 2 will land one of these and confirm the residual rejection rate drops to zero.

## 4. Defect found in run-1, fixed before run-2

Initial 70-row run produced **35 errors** (50% failure rate) concentrated in three families:

- `tau2_retail` (10/10 errored)
- `tau2_airline` (10/10 errored)
- `tau2_telecom` (15/15 errored before the one residual relative-date issue)

Common error pattern:

```
world_patch.files.`household/HH-7/orders.json`
  Input should be a valid dictionary or instance of NaturalizedFilePatch
```

Root cause: gpt-5.2 returned the rewritten content of list-shaped resource files (`orders.json`, `lines.json`, `reservation.json`) verbatim as a JSON list, not wrapped in `{content: "<json string>"}`. The Pydantic model `NaturalizedFilePatch` already had a `_coerce_string_patch` validator that handled string and dict inputs but not lists.

The other three families (`marble_research`, `marble_bargaining`, `wildclaw_social`) have markdown / text resources, so gpt-5.2 returned content as a string and the existing string-coercion path passed.

Fix landed in `clawsocialarena/generator/naturalization.py:NaturalizedFilePatch._coerce_string_patch`:

```python
if isinstance(value, list):
    return {
        "content": json.dumps(value, sort_keys=True, ensure_ascii=False),
        "expected_final_state": "unchanged",
    }
```

Regression test: `test_naturalization_patch_serializes_list_shaped_file_body` in `tests/test_generator/test_naturalization.py` pins this with a tau2_retail-shaped list payload. All 32 naturalization tests + 27 orchestrator tests pass after the fix.

Cost of the failed run-1: **$0.69** (35 successful naturalizations + 35 fast failures that still consumed input tokens). Backup artifacts retained at `benchmark/phase5/pilot/BATCH_01_smoke_*_run1_35errors.{json,jsonl}` for the codex review.

## 5. Cost projection for the rest of the pilot

| stage | rows | projected cost (naturalization only) |
|-------|-----:|-------------------------------------:|
| Run-Batch 1 (this) | 70 | $1.54 (observed, upper bound) |
| Run-Batch 2 (task diversity) | 140 | ~$3 |
| Run-Batch 3 (tier 2) | 210 | ~$4.50 |
| Run-Batch 4 (tier 3) | 210 | ~$4.50 |
| Run-Batch 5 (supplementary) | 50 | ~$1.50 |
| **Total naturalization** | **680** | **~$15** |

This assumes per-row cost stays around $0.022. Prompt caching across the 3 task variants of each base bundle should keep the average down. Run-Batches 3 and 4 will probably cost slightly less per row because they share many of the same skeleton fields with Run-Batches 1 and 2 (only the tier transformation changes, so the cache hits more).

The agent-loop simulation (gpt-4.1-mini) is a separate cost line that lands in Run-Batches 2..5 when the loop is wired. Estimated additional spend: ~$5–10 for the full pilot.

## 6. Coverage gates passed

- **Family coverage:** all 6 family packs naturalized ≥ once at task=0/tier=1; no family is broken at the schema level.
- **Attack mode coverage:** all 5 modes round-trip (no_attacker + collaboration + security + privacy + governance).
- **Cell coverage:** all 14 cells exercised exactly once (1 task × 1 tier × 5 modes per cell).
- **Cost cap:** $1.54 (upper bound) vs. the $5 estimate the user agreed to.
- **Orchestrator scaffolding:** per-row try/except correctly isolated the one failure; rate denominators correctly dropped the errored row instead of counting it as `task_success=False`.

## 7. Open follow-ups for later batches

1. **Relative-date noncompliance handling.** Targeted retry or deterministic post-sanitize rewrite on `persona_notes.*` for the one row that errored. The prompt already instructs absolute-dates-only twice; this is model noncompliance, not missing guidance.
2. **Live agent loop wiring.** Run-Batch 2 will extend `LiveScenarioExecutor` with a generic gpt-4.1-mini agent loop that drives each scenario through `Session.build` for a few turns, scores `env_assertions`, and reports `attack_success` against the four non-baseline modes.
3. **Container-shape drift hardening.** `NaturalizedWorldPatch.files` and `NaturalizedWorldPatch.databases` are typed as `dict[str, ...]` with no top-level list→dict coercion. If gpt-5.2 later emits `files` as `[{path, content}, ...]` or `databases` as a top-level list, validation will fail without a clear hint. Add a defensive `model_validator(mode="before")` that converts the common list shape into the keyed-dict shape. Not blocking Run-Batch 2 (no evidence of this in the artifacts), but worth landing before harder tiers / supplementary stratum push the model into more varied output shapes.
4. **Provider-side prompt cache observability.** Reuse across the 5 attack modes of one base task currently depends on OpenAI's prompt cache, not local memoization. Cache hits show up in `cached_input_tokens`; Run-Batch 2 should report the cache-hit ratio as a first-class metric so we can decide whether to add local memoization for cost control.

## 8. Files inventory

```
benchmark/phase5/scaffold/                           (S3 manifest output, 680-row)
  phase5_manifest.json
  phase5_base_index.json
  phase5_variants_index.json
  CD-A-marble_research/task0/tier1/scenario.json
  ... (and 125 more base bundles + attack variants)

benchmark/phase5/pilot/                              (Run-Batch 1 output)
  BATCH_01_smoke_REPORT.json                         (full aggregated summary)
  BATCH_01_smoke_RESULTS.jsonl                       (70 rows × ScenarioResult)
  BATCH_01_smoke_REPORT_run1_35errors.json           (backup of pre-fix run)
  BATCH_01_smoke_RESULTS_run1_35errors.jsonl         (backup of pre-fix run)

docs/phase_5/BATCH_01_smoke_REPORT.md                (this file)
```

Code changes in this batch:

```
clawsocialarena/generator/naturalization.py    (NaturalizedFilePatch._coerce_string_patch: list handling)
clawsocialarena/orchestrator/phase5_live_executor.py  (LiveScenarioExecutor.execute body)
clawsocialarena/orchestrator/phase5_orchestrator.py   (fh.flush() per row for progress monitoring)
scripts/run_phase5_pilot.py                    (--limit N flag for small live validations)

tests/test_generator/test_naturalization.py    (+1 regression test)
tests/test_orchestrator/test_phase5_live_executor.py  (+5 tests, mocked JsonClient)
tests/test_orchestrator/test_phase5_executor.py       (updated raise-test for new live surface)
```

## 9. Verdict request

Run-Batch 1's coverage gates passed (every family × attack-mode pair naturalizes; cost under budget; orchestrator scaffolding behaves correctly under both clean and errored rows). One residual sanitizer rejection identified for Run-Batch 2 follow-up; pre-fix run-1 artifacts retained for audit. Re-running codex review now.

## 10. Revision r1 — close codex's audit-precision blocker

Codex's first re-review (verdict: REVISE) flagged one blocker on this report: the on-disk JSONL did not preserve `extra.raw_usage` for the errored row, so my cost computation script silently dropped the 2,696 / 882 tokens that the failed naturalization had still consumed. The headline `$1.52` understated the true cost.

Fix landed in `clawsocialarena/orchestrator/phase5_live_executor.py:_errored_result`: the function now stores `raw_usage = dict(naturalization_usage)` inside `extra` whenever the validation-error path is taken. Successful rows already had this; errored rows did too in the in-memory `naturalization_usage` field but lost the raw_usage breakdown on persistence. Future batches will have a complete cost picture without manual reconstruction.

For Run-Batch 1's already-persisted artifact, the cost was recomputed from the aggregated `naturalization_usage` field on the errored row (2,696 prompt + 882 completion). The corrected cost is **$1.54 upper bound** (cached split unknown for the one errored row; the cached portion would only reduce this figure). Headline metrics in section 1 of this report reflect the corrected number.

The codex review also pushed back on my "one-line prompt nudge for relative dates" suggestion (section 3): the existing system prompt already says "absolute dates only" twice, so the residual rejection is model noncompliance, not missing guidance. Section 3 and section 7 now propose a targeted retry or deterministic post-sanitize rewrite instead.

No retest needed; the affected code path was the cost rollup script and the executor's error-result builder. The 27 orchestrator + 32 naturalization tests pass after the fix.
