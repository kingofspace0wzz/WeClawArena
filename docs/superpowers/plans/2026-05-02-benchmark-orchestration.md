# Benchmark Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a non-interactive benchmark orchestration runner that automatically performs readiness checks before canonical benchmark generation.

**Architecture:** Keep the deterministic scaffold generator responsible for planning and materialization. Add `scripts/orchestrate_benchmark.py` as the workflow layer that materializes into a temp tree for `prepare`, validates dataset contracts, runs configured checks, writes JSON reports, and only writes canonical data from `generate --yes`.

**Tech Stack:** Python 3.11, argparse, subprocess, tempfile, JSON reports, existing scenario validator, existing generator planner/materializer, pytest.

## Correction as of 2026-05-05

The original 550-variant orchestration contract is now a pre-calibration scaffold contract. The current orchestration target is the 680-variant balanced difficulty pilot: 630 main variants, 25 hard variants, 20 episode-graph variants, and 5 audit challenge cases. The non-audit resource-backed count is 675. Orchestration reports must also verify task schema v0 fields, designed difficulty tier, task-success spec, and source-pattern metadata before declaring `READY_TO_GENERATE`.

---

## Task 1: Add Orchestration Tests

**Files:**
- Create: `tests/test_scripts/test_orchestrate_benchmark.py`

- [x] **Step 1: Test prepare report**

Write a test that calls:

```python
orchestrate_benchmark.main([
    "prepare",
    "--seed", "1200",
    "--version", "v1.0.0",
    "--report-dir", str(report_dir),
])
```

Patch command execution to return success for external checks. Assert the report exists, has `status == "READY_TO_GENERATE"`, `generation_status == "READY_TO_GENERATE"`, validates `scenario_count == 680`, records `resource_count == 675`, reports ASB-backed world-pack construction metadata, reports task schema v0 coverage, reports `realism_status == "worldpack_draft"`, and keeps `release_ready == false`.

- [x] **Step 2: Test generate gate**

Write a test that calls `generate` without `--yes` and asserts it returns `2`, does not create output data, and explains that `--yes` is required.

- [x] **Step 3: Test generate with explicit approval flag**

Write a test that calls:

```python
orchestrate_benchmark.main([
    "generate",
    "--yes",
    "--seed", "1200",
    "--version", "v1.0.0",
    "--out", str(out),
])
```

Patch command execution to return success for external checks. Assert `out/index.json` exists, `out/build_report.json` exists, report generation status is `GENERATED`, and `release_ready == false` while realism remains `worldpack_draft`.

- [x] **Step 4: Test failed check reporting**

Patch command execution so one check fails. Assert the command returns `1`, report status is `FAILED`, and the failed command is recorded.

- [x] **Step 5: Run red tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_scripts/test_orchestrate_benchmark.py -q
```

Expected result: tests fail because `scripts/orchestrate_benchmark.py` does not exist yet.

## Task 2: Implement Orchestrator

**Files:**
- Create: `scripts/orchestrate_benchmark.py`

- [x] **Step 1: Build CLI**

Implement subcommands:

```bash
prepare --seed 1200 --version v1.0.0 --report-dir benchmark/orchestration/latest
generate --seed 1200 --version v1.0.0 --out benchmark/scenarios/v1.0.0 --yes
```

- [x] **Step 2: Implement materialization helper**

Call the active scaffold generator with `--materialize-benchmark --strata all` into either a temp dir (`prepare`) or the requested output dir (`generate`).

- [x] **Step 3: Implement dataset contract checks**

Verify:

```python
scenario_count == 680
strata == {"main": 630, "hard": 25, "episode_graph": 20, "audit_challenges": 5}
resource_count == 675
resource strata == {"main": 630, "hard": 25, "episode_graph": 20}
```

Validate every indexed bundle with `validate_bundle`. For main rows, also assert that `construction_manifest` includes `task_schema_version`, `designed_difficulty_tier`, `actors`, `benign_task_objective`, `task_success_spec`, `audit_events`, and `source_pattern`.

- [x] **Step 4: Implement external checks**

Run focused checks through subprocess:

```bash
.venv/bin/python -m pytest tests/test_scripts/test_generate_benchmark_scaffold.py tests/audit_challenges -q
.venv/bin/python -m ruff check scripts/generate_benchmark_scaffold.py scripts/orchestrate_benchmark.py tests/test_scripts/test_generate_benchmark_scaffold.py tests/test_scripts/test_orchestrate_benchmark.py clawsocialarena/generator/resource_overlays.py
.venv/bin/python -m mypy scripts/generate_benchmark_scaffold.py scripts/orchestrate_benchmark.py tests/test_scripts/test_generate_benchmark_scaffold.py tests/test_scripts/test_orchestrate_benchmark.py clawsocialarena/generator/resource_overlays.py
```

Allow an optional `--run-full-suite` flag that also runs `.venv/bin/python -m pytest -q`.

- [x] **Step 5: Implement reports**

Write `report.json` for `prepare` and `build_report.json` for `generate`. Include command results, dataset summary, validation counts, report status, seed, version, and output path.

- [x] **Step 6: Run green tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_scripts/test_orchestrate_benchmark.py -q
```

Expected result: orchestration tests pass.

## Task 3: Run Orchestration

**Files:**
- Create/update: `benchmark/orchestration/latest/report.json`
- Update: `benchmark/scenarios/v1.0.0/build_report.json`

- [x] **Step 1: Run prepare**

Run:

```bash
.venv/bin/python scripts/orchestrate_benchmark.py prepare --seed 1200 --version v1.0.0
```

Expected result: status `READY_TO_GENERATE`, generation status `READY_TO_GENERATE`, construction metadata present, and release readiness false.

- [x] **Step 2: Run generate**

Run:

```bash
.venv/bin/python scripts/orchestrate_benchmark.py generate --seed 1200 --version v1.0.0 --out benchmark/scenarios/v1.0.0 --yes
```

Expected result: generation status `GENERATED`, canonical benchmark is regenerated, and release readiness remains false until human review upgrades the realism status.

- [x] **Step 3: Verify the new workflow**

Run:

```bash
.venv/bin/python -m pytest tests/test_scripts/test_orchestrate_benchmark.py tests/test_scripts/test_generate_benchmark_scaffold.py -q
.venv/bin/python -m ruff check scripts/orchestrate_benchmark.py tests/test_scripts/test_orchestrate_benchmark.py
.venv/bin/python -m mypy scripts/orchestrate_benchmark.py tests/test_scripts/test_orchestrate_benchmark.py
```

Expected result: all commands pass.

## Task 4: Full Regression

**Files:**
- No planned edits.

- [x] **Step 1: Run full suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected result: no regressions beyond known skips.

## Self-Review

- The orchestration runner is non-interactive.
- Canonical generation is gated by a command flag, not a prompt.
- The runner reports every gate in JSON so CI and humans can inspect failure causes.
- `generate_benchmark_scaffold.py` stays focused on deterministic materialization.
