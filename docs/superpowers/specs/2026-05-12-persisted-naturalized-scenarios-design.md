# v2 Persisted Naturalized Scenarios -- Design Spec

- **Date**: 2026-05-12
- **Author**: Prince (brainstorm with Claude Code)
- **Status**: brainstormed; pending implementation plan
- **Predecessor**: docs/superpowers/specs/2026-05-06-clawsocialarena-v2-benchmark-design.md
- **Parent task**: Phase-5 substrate rebuild after Stream A/B/B.2 and the four stress recipes

## Summary

Replace the current ephemeral naturalization step with a two-stage pipeline. The generator emits 42 pre-naturalization base bundles under `benchmark/phase5/scaffold/<cell>/task<N>/` (no tier dim). A new `scripts/publish_phase5_scenarios.py` runs gpt-5.2 naturalization once per base and writes the rendered bundle to an immutable, version-tagged store at `benchmark/scenarios/v2.0.0/<base_id>/`. The store is committed and pushed to the repo as a benchmark artifact. The live executor reads from the v2 store at run time, materializes a per-run scratch copy under `benchmark/phase5/pilot/<run>/variants/<variant_id>/`, applies the stress-recipe overlay from `STRESS_RECIPE_REGISTRY`, runs the scenario, and leaves all trajectories (session.db, cassettes, resource mutations) in the run-time scratch dir. R-B 1 to R-B 5 are redesigned around attack regime and cross-model axes instead of the retired difficulty-tier axis.

## Goals

1. Naturalize once, run many times. Naturalization is no longer in the per-scenario hot path.
2. Drop the difficulty-tier dimension. Task variants and stress recipes carry the workload that tier inflation was meant to provide.
3. Make the published scenarios store an immutable, committable artifact. Reproducibility from a fresh clone, no shared scratch state mutated across runs.
4. Per-run trajectories live in their own pilot dir (`pilot/<run>/variants/<variant_id>/phase5_session/`), so a completed run's full action log survives subsequent runs.
5. Redesign R-B 1 to R-B 5 around dimensions that survive the tier drop: attack regime (standard vs stress), agent-model selection, and supplementary strata.
6. Build with headroom for the content expansion in specs 2 and 3 (~85 bases / ~425 variants after WildClaw social tasks and `tau2_banking_knowledge` land).

## Non-Goals

- New attack recipes. The four stress recipes landed in a sibling effort; this spec does not modify them.
- Repo-wide refactor of `clawsocialarena.orchestrator.phase5_*` paths. The `phase5_` prefix stays. A future cleanup spec can rename if needed.
- LLM-judge changes. The judge module landed tonight and is unaffected.
- Pack content additions. WildClaw 5 new tasks and `tau2_banking_knowledge` are spec 2 and spec 3 respectively. Spec 1 ships with the existing 6 packs.

## Background

The current pipeline runs gpt-5.2 naturalization at the start of every live executor row. For R-B 2 alone (140 rows), that re-spends naturalization tokens on rows whose base scenario has not changed. Tonight's tau2_telecom re-sim showed the naturalization step is itself working correctly (0% to 73.3% task_success after the schema-description fix), but it remains in the per-scenario hot path. Persisting the rendered output cuts naturalization cost from per-row to per-base.

Separately, the existing run-batch structure binds R-B 3 and R-B 4 to tiers 2 and 3 of the difficulty-tier system in `clawsocialarena/generator/difficulty_tier.py`. The tier system varies max_turns and opening-message pressure prose; it does not introduce structurally distinct attack regimes. With the four stress recipes (security indirect resource injection, privacy adaptive exfiltration, governance poisoned consent, collaboration adaptive peer) doing the heavy lifting on attack diversity, tiers no longer earn their cost in the benchmark.

The legacy `benchmark/scenarios/v1.0.0/` store (183 MB, 1260 dirs) was built from an older family taxonomy (scheduling, consensus, inference, coalition) that does not overlap with the current 6 packs. It is kept as a frozen reference; spec 1 does not migrate it.

## Architecture

Three layers, three locations:

```
Pre-naturalization scaffold (build-time input)
benchmark/phase5/scaffold/<cell>/task<N>/
  scenario.json           pre-LLM, structural only
  scenario.gt.json
  governance/
  mcp/
  resources_initial/
  family_pack_context.json
42 base bundles (14 cells x 3 tasks; tier dim removed)
                        |
                        | scripts/publish_phase5_scenarios.py
                        | gpt-5.2 naturalization, hash-cached
                        v
Published v2 store (immutable, version-tagged, committed to repo)
benchmark/scenarios/v2.0.0/<base_id>/
  scenario.json           post-naturalization
  scenario.gt.json
  personas/
  mcp/
  governance/
  resources_initial/
  family_pack_context.json
  naturalization_record.json   input_hash, model, ts, tokens
benchmark/scenarios/v2.0.0/manifest.json
  {rows: [{variant_id, base_id, family_id, attack_mode, ...}]}
                        |
                        | run_phase5_pilot.py --store ... --filter ...
                        | live executor: for each row, materialize
                        v
Run-time working dirs (per-run, per-variant scratch)
benchmark/phase5/pilot/<run_name>/
  BATCH_REPORT.json
  RESULTS.jsonl
  run.log
  variants/<variant_id>/
    scenario.json           base + stress overlay
    resources/              mutated by tool dispatch at run time
    resources_initial/
    phase5_session/         session.db, shadow.db, cassette.jsonl
```

### Key invariants

- The v2 store is immutable. Nothing in the runtime touches files under `benchmark/scenarios/v2.0.0/`. Republishing requires a new version tag (`v2.0.1`).
- The runtime always copies the base bundle into the per-run variants tree before mutating anything. Session DBs, cassettes, and resource mutations all land in `pilot/<run>/variants/<variant_id>/`.
- Naturalization runs once per base (42 calls at spec 1 scale). Attack overlays are applied at run time from `STRESS_RECIPE_REGISTRY`. The hash-based publish cache skips bases whose pre-naturalization input is unchanged.
- The tier dim is fully removed from `phase5_base_generator.py`. `difficulty_tier.py` and `task_difficulty.py` collapse to legacy compatibility stubs.

## Components and File Changes

### 1. Generator: drop tier dim

**`clawsocialarena/generator/phase5_base_generator.py`**
- Remove the `for tier_index in (1, 2, 3): ...` outer loop. Builds 42 base records (14 cells x 3 tasks).
- `BaseBundleRecord` keeps `task_index` and `task_label`; drops `tier_index` and `tier_name`.
- `bundle_dir` template changes from `<cell>/task<N>/tier<K>` to `<cell>/task<N>`.

**`clawsocialarena/generator/difficulty_tier.py`**
- Reduced to a legacy stub. `TierSpec`, `apply_tier`, `tier_for` remain importable but always return the tier-1 (easy) profile. Module docstring marks it deprecated.

**`clawsocialarena/generator/task_difficulty.py`**
- Same treatment: `difficulty_profile()` returns the tier-1 profile regardless of the `tier` arg.

**`scripts/generate_benchmark_scaffold.py`** (v1.0.0 generator) -- untouched.

### 2. Publish script (new)

**`scripts/publish_phase5_scenarios.py`** (new, ~400 LOC)

CLI:
```
python scripts/publish_phase5_scenarios.py \
    --scaffold-dir benchmark/phase5/scaffold \
    --store-dir benchmark/scenarios/v2.0.0 \
    --naturalization-model gpt-5.2 \
    --max-workers 4 \
    [--base-id <id>]      # publish a single base
    [--force]              # ignore cache, re-naturalize
    [--dry-run]            # print plan, don't call gpt-5.2
```

Per-base flow:

1. Read pre-nat `<scaffold>/<cell>/task<N>/{scenario.json, scenario.gt.json, ...}`.
2. Compute `input_hash = sha256(canonicalized_concat(scenario.json, scenario.gt.json, family_pack_context.json, ...))`.
3. Look up `<store>/<base_id>/naturalization_record.json`. If present, `input_hash` matches, and `--force` is not set: skip.
4. Otherwise, call gpt-5.2 naturalization using the existing naturalization template machinery (`clawsocialarena/generator/templates/`).
5. Write the naturalized bundle to `<store>/<base_id>/`:
   - `scenario.json` (post-naturalization)
   - `scenario.gt.json`
   - `personas/<agent_id>.system.md` + `<agent_id>.tools.json`
   - `mcp/` (family-pack tool registration)
   - `governance/` (mandates + scopes)
   - `resources_initial/` (seed sqlite state per user)
   - `family_pack_context.json`
   - `naturalization_record.json` containing:
     ```json
     {
       "input_hash": "sha256:...",
       "naturalization_model": "gpt-5.2",
       "naturalization_run_ts": "2026-05-12T...",
       "naturalization_tokens_used": {"prompt": ..., "completion": ...},
       "naturalization_template_version": "v1"
     }
     ```
6. Concurrency: `ThreadPoolExecutor(max_workers=4)` over bases (gpt-5.2 calls are I/O-bound).

After all bases publish, emit `<store>/manifest.json`:
```json
{
  "version": "v2.0.0",
  "n_bases": 42,
  "n_modes": 5,
  "n_variants": 210,
  "naturalization_model": "gpt-5.2",
  "rows": [
    {
      "variant_id": "<base_id>__<mode>",
      "base_id": "...",
      "family_id": "...",
      "cell_id": "...",
      "task_index": ...,
      "attack_mode": "...",
      "bundle_dir": "<base_id>"
    }
  ]
}
```

### 3. Runtime overlay (extract from one-shot script)

**`clawsocialarena/attacks/runtime_overlay.py`** (new, ~150 LOC)

Pure function:
```
def materialize_runtime_variant(
    *,
    store_dir: Path,
    base_id: str,
    attack_mode: str,
    run_dir: Path,
    recipe_registry: dict[str, StressRecipe] = STRESS_RECIPE_REGISTRY,
) -> Path:
    ...
```

Behavior:

- Copies `<store_dir>/<base_id>/` to `<run_dir>/variants/<variant_id>/` (full copytree, not symlinks).
- If `attack_mode != "no_attacker"`, looks up the matching stress recipe (`_AXIS_TO_RECIPE[attack_mode]`), calls `recipe.build_variant_artifacts(...)`, applies the artifacts (file writes, db inserts, db updates, scenario mutations) to the copy.
- Returns the working `variant_dir`.

The legacy `resources/`-prefix path normalization from tonight's one-shot script is preserved here.

**`scripts/regenerate_phase5_stress_variants.py`** (existing) becomes a thin CLI wrapper that calls `materialize_runtime_variant`. Kept for ad-hoc overlay smoke testing.

### 4. Live executor: store-mode

**`clawsocialarena/orchestrator/phase5_live_executor.py`**

- New constructor args:
  - `store_dir: Path` (location of `scenarios/v2.0.0/`)
  - `run_dir: Path` (location of `pilot/<run>/`)
- Replace the existing `bundle_dir`-resolution with `materialize_runtime_variant(...)`.
- Session is built against the materialized variant dir; session.db lands in `<run_dir>/variants/<variant_id>/phase5_session/`.
- Drop the `_restore_resources_from_snapshot` complexity. The per-run variant tree is fresh each run, so the destructive restore is unnecessary.
- The runtime naturalization step is removed. The v2 store is naturalized.

### 5. Manifest selectors and R-B redesign

**`clawsocialarena/orchestrator/phase5_run_batches.py`**

Replace tier-tied selectors with the new attack-regime / cross-model dimensions:

| Batch | Selector | Initial rows (after spec 1) | Final rows (after specs 2+3) | Purpose |
|---|---|---|---|---|
| R-B 1 (smoke) | 1 row per family x 5 modes | 30 | 35 | sanity, fast |
| R-B 2 (standard) | all bases x 5 modes, standard recipes | 210 | ~425 | reproduces current R-B 2 history |
| R-B 3 (stress) | all bases x 4 stress axes, baseline reuses R-B 2 | 168 | ~340 | tests the new stress recipes |
| R-B 4 (cross-model) | R-B 2's selection x gpt-5.2 as agent | 210 | ~425 | optional; cost-gated |
| R-B 5 (supplementary) | hard + episode-graph + audit | 50 | 50 | unchanged |

**`scripts/run_phase5_pilot.py`**

- Add `--store <path>` (default: `benchmark/scenarios/v2.0.0`).
- Add `--filter <key>=<value>[,<key>=<value>...]` for ad-hoc slices. Keys: `family`, `cell`, `task`, `mode`, `base_id`. Filters compose with the batch selector (filter ANDed with batch row set).
- Add `--list-rows` subcommand that prints the filtered rows without running.
- `--batch {1..5}` keeps working, now backed by the new selector definitions.

**`clawsocialarena/orchestrator/phase5_orchestrator.py`**

- `RunBatchSummary` keeps its name (the run-batch concept survives). The per-axis attack metric columns landed tonight (`attack_detection_rate_*`, `baseline_false_positive_rate_*`, `attack_success_rate_*`) carry over unchanged.

### 6. Migration utility

**`scripts/migrate_scaffold_drop_tier.py`** (new, ~60 LOC)

- Walks `benchmark/phase5/scaffold/`, deletes `tier2/` and `tier3/` subdirs cleanly, regenerates `phase5_base_index.json` and `phase5_variants_index.json` with the 42-base row set.
- `--dry-run` flag for previewing.

## Data Flow

```
0. Pre-flight (one-time)
   generator -> 42 base bundles in phase5/scaffold/<cell>/task<N>/

1. Publish (one-time per content change)
   publish_phase5_scenarios.py:
     for each base in scaffold/:
       hash = sha256(scenario.json + scenario.gt.json + ...)
       if scenarios/v2.0.0/<base_id>/naturalization_record.json.input_hash == hash: skip
       else: call gpt-5.2; write fully-naturalized bundle + record
     emit scenarios/v2.0.0/manifest.json

2. Commit-and-push (acceptance gate)
   git add benchmark/scenarios/v2.0.0/
   git commit -m "publish v2.0.0 naturalized scenarios store"
   git push

3. Run (every experiment)
   run_phase5_pilot.py --store scenarios/v2.0.0 --batch 2 --out pilot/<run>/:
     a. Load manifest, apply batch selector + --filter slices
     b. For each (base_id, attack_mode) row:
        - materialize_runtime_variant(store, base_id, mode, run_dir)
          - copytree scenarios/v2.0.0/<base_id>/ -> pilot/<run>/variants/<variant_id>/
          - if mode != no_attacker: apply stress recipe overlay to the copy
        - Live executor builds Session against pilot/<run>/variants/<variant_id>/
        - Runs agent loop, attacker peer (if adaptive), tool dispatch
        - Sessions/cassettes land in pilot/<run>/variants/<variant_id>/phase5_session/
        - All resource mutations land in pilot/<run>/variants/<variant_id>/resources/
        - Scoring (env_assertions, heuristic axes, SAF)
     c. Aggregator writes pilot/<run>/BATCH_REPORT.json + RESULTS.jsonl

4. Post-hoc rescore (optional)
   python -m clawsocialarena.eval.llm_judge \
       --batch-results pilot/<run>/BATCH_*.jsonl \
       --store scenarios/v2.0.0 \
       --out pilot/<run>/BATCH_*.llm_judge.jsonl
   Reads pilot/<run>/variants/<variant_id>/phase5_session/session.db for trajectories.
```

## Error Handling

| Failure stage | What it looks like | Handling |
|---|---|---|
| Publish: scaffold base missing required field | KeyError on `scenario.gt.json` parse | Skip base; log to `publish_failures.jsonl`; non-zero exit if any failures. |
| Publish: gpt-5.2 call fails or times out | Naturalization client raises | Retry up to 3 times with exponential backoff; on final failure, write a record file with `status=failed` and skip; manifest excludes failed bases. |
| Runtime: missing base in store | `scenarios/v2.0.0/<base_id>/` not a dir | Errored row, `phase5_failure_stage=store_lookup`, no other rows affected. |
| Runtime: overlay artifact write fails | sqlite or file write error | Errored row, `phase5_failure_stage=overlay_apply`, full error captured in `extra.overlay_failure`. |
| Runtime: stress recipe missing for axis | Mode is e.g. `security` but no registry entry | Fail the row explicitly (`extra.overlay_failure_stage=recipe_lookup`); do not silently fall back to legacy `prompt_injection`. Publish step verifies all 4 axes have registered recipes before emitting the manifest. |
| Runtime: variant_dir already exists from a prior run | First-run mode; should be empty | Re-running the same `--run-name` reuses the existing variant dir. The runtime honors `--force-overwrite` to wipe first. Default behavior: a variant_dir is considered "complete" when it contains `phase5_session/session.db` AND the parent run's `RESULTS.jsonl` already has a non-errored row for this `variant_id`. Complete variants are skipped (idempotent reruns); incomplete ones are `rmtree`'d and re-materialized. |
| Runtime: session.db write fails (disk full, perms) | SQLAlchemy / sqlite OperationalError | Errored row, `phase5_failure_stage=session_init`. |
| Aggregator: zero rows ran | RunBatchSummary fields would divide by zero | Existing behavior preserved -- rates are None, not 0/0. |

Per-row failures never abort the batch. Each row's error is captured in the RESULTS.jsonl with `phase5_failure_stage` so the user can audit which rows ran and which fell out.

## Testing

| Test | Path | Scope |
|---|---|---|
| Tier-drop count | update existing `tests/test_generator/test_phase5_base_generator.py` | Assert base count = 42 and `bundle_dir` matches `<cell>/task<N>` pattern. |
| Publish cache | new `tests/test_scripts/test_publish_phase5_scenarios.py::test_publish_skips_when_input_hash_matches` | Mock naturalization client; assert second run with unchanged input does zero calls. |
| Publish force flag | same file::`test_publish_force_flag_bypasses_cache` | Mock naturalization client; assert second run with `--force` does the call regardless. |
| Publish manifest shape | same file::`test_publish_emits_manifest_with_expected_rows` | After publishing a 2-base fixture, assert `manifest.json` has 10 rows (2 bases x 5 modes) sorted by `variant_id`. |
| Filter parsing | new `tests/test_scripts/test_run_phase5_pilot_filters.py::test_filter_parses_family_mode_task` | Assert `--filter family=tau2_telecom,mode=privacy` returns the right rows from a fixture manifest. |
| Filter empty | same file::`test_filter_empty_returns_all` | No filter returns the full manifest. |
| Live executor store-mode smoke | new `tests/test_orchestrator/test_phase5_live_executor_store_mode.py::test_smoke_4_row_mock_run` | 1-row mock-mode integration test: load store, materialize variant, run mock agent, assert session.db lands in `pilot/<run>/variants/<variant_id>/phase5_session/`. |

Two existing tests updated:

- `tests/test_generator/test_phase5_base_generator.py`: existing count assertion changes from 126 to 42.
- `tests/test_orchestrator/test_phase5_live_executor_full_mode.py`: executor constructor args updated; existing assertions on session.db location switched to the new `run_dir/variants/` path.

Not in scope (already covered by existing tests):

- Stress recipe content -- 74 tests in `tests/test_attacks/` landed tonight.
- LLM judge -- 8 tests in `tests/test_eval/test_llm_judge.py` landed tonight.
- Runtime overlay artifact generation -- covered by the 74 recipe tests; the extracted function is a thin wrapper.

Total new tests: 7. Two existing tests updated for arg or count changes. Mock-mode end-to-end and live publish smoke are excluded from CI; the live smoke is a manual acceptance step.

Repo-wide regression target: tonight's baseline of 1632 passing tests must hold or grow, never shrink.

## Acceptance Criteria

The spec is implementable in roughly this order. Each numbered step is a discrete acceptance gate.

1. Tier-drop generator change lands; `tests/test_generator/test_phase5_base_generator.py` asserts the new count = 42. Migration utility script wipes `tier2/` and `tier3/` cleanly.
2. `scripts/publish_phase5_scenarios.py` lands with the 4 unit tests passing. Live smoke (one real gpt-5.2 call on a single tau2_telecom base) confirms the published bundle is byte-identical-shape to what the runtime expects.
3. Mass publish runs against the 42-base scaffold. `benchmark/scenarios/v2.0.0/` is fully populated, `manifest.json` lists 210 rows, `naturalization_record.json` is present for every base.
4. `benchmark/scenarios/v2.0.0/` is committed and pushed to the repo. `.gitignore` is amended to add `!benchmark/scenarios/**/resources_initial/**/*.sqlite` so the seed databases ship with the store while `pilot/<run>/.../session.db` stays ignored.
5. Runtime overlay extracted into `clawsocialarena/attacks/runtime_overlay.py`. The one-shot script `scripts/regenerate_phase5_stress_variants.py` switches to call the new function.
6. Live executor store-mode lands with `--store` flag and per-run variant materialization. The store-mode smoke test passes.
7. Filter parser lands in `run_phase5_pilot.py` with the 2 unit tests passing.
8. R-B 1 smoke (30 rows, gpt-4.1-mini agent, mock OR live) succeeds end-to-end. Acceptance criterion: at least 25 of 30 rows produce a definite `task_success` outcome with no `phase5_failure_stage` outside `agent_loop`.

After step 8 passes, R-B 2 / R-B 3 / R-B 4 are run as planned in the parent project.

## .gitignore Adjustment

Add to `.gitignore`:
```
!benchmark/scenarios/**/resources_initial/**/*.sqlite
```

The existing `*.sqlite` and `*.db` patterns continue to ignore:

- `benchmark/phase5/scaffold/**/personal.sqlite` (pre-naturalization scratch state)
- `benchmark/phase5/pilot/<run>/variants/<variant_id>/phase5_session/session.db` (run-time DBs)
- `benchmark/phase5/pilot/<run>/variants/<variant_id>/resources/**/*.sqlite` (run-time mutated state)

Only the seed databases inside the published v2 store are committed.

## Migration Plan

### Existing `benchmark/phase5/scaffold/`

The scaffold is regenerated by the generator script with the tier-drop change. The migration utility (`scripts/migrate_scaffold_drop_tier.py`) handles existing scaffolds in place: walks `<cell>/task<N>/`, deletes `tier2/` and `tier3/` subdirs, renames `tier1/` contents up one level so the layout matches the new `<cell>/task<N>/` pattern, regenerates `phase5_base_index.json`. The user can also delete and regenerate from scratch; the migration script is convenience only.

### Existing `benchmark/phase5/pilot/`

Existing pilot dirs (`rb2_streamAB_v2/`, `telecom_fix_smoke/`, etc.) stay as read-only legacy artifacts. The new pipeline writes into `pilot/v2_*` naming (e.g., `pilot/v2_rb2_standard/`) so historical and new runs do not interleave.

The reporting / analysis docs that reference legacy pilot dirs (e.g., `docs/phase_5/BATCH_02_*.md`) stay as historical record. New analyses live under `docs/phase_5/v2_*.md`.

### Legacy `benchmark/scenarios/v1.0.0/`

Untouched. The 1260-dir legacy store represents a different family taxonomy (scheduling, consensus, inference, coalition) that does not overlap with the current 6 packs. Spec 1 does not migrate or delete it. A separate "legacy retirement" task can deprecate it later.

## Open Questions and Risks

1. **Naturalization template versioning**. The `naturalization_template_version` field in `naturalization_record.json` is a string we set ourselves. If we later change the template, every base's `input_hash` stays the same but the rendered output drifts. The conservative interpretation: any template change requires a `--force` republish and a version bump. The spec defers a richer template-version dependency tree until specs 2 or 3 motivate it.

2. **gpt-5.2 deprecation**. If OpenAI deprecates gpt-5.2 before R-B 4 completes, the published store's `naturalization_model` field becomes a historical record only. New republishes would need a different model. Risk is small; the published store stays valid even after the model retires.

3. **Disk usage**. 42 bases x ~5 MB each = ~250 MB for the v2 store at spec 1 scale. After specs 2+3 (~85 bases) the store grows to ~500 MB. Manageable but worth noting.

4. **Cross-model R-B 4 cost**. gpt-5.2 as the agent (R-B 4) on ~210 rows at ~16 turns x ~2k tokens/turn = ~6.7M tokens. At gpt-5.2 pricing this is a real chunk of budget. Optional / cost-gated in the R-B table.

5. **Adaptive peer cost in R-B 3**. The privacy and collaboration stress recipes spin up a runtime peer LLM at gpt-4.1-mini. Per-turn ~1k extra tokens; 6-turn budget x 84 adaptive rows = ~500k tokens added to R-B 3. Already covered by existing budget.

6. **Hash collision on canonical input**. sha256 collision probability is negligible. If the user reports an incorrect skip, `--force` bypasses the cache.

7. **`benchmark/scenarios/v2.0.0/` size in git**. Roughly 250 MB at spec 1 scale; could push toward 500 MB after specs 2+3. Git handles this size, but git LFS may be worth considering before scaling further. Out of scope for spec 1.

## Out of Scope

- Generating WildClaw 5 new social tasks (spec 2).
- Generating `tau2_banking_knowledge` as a 7th family pack (spec 3).
- Cross-model studies beyond R-B 4 (e.g., open-weights agents).
- Renaming the `phase5_` prefix to a clean `runtime`-style namespace.
- LLM judge architectural changes.
- Stress recipe content modifications.
