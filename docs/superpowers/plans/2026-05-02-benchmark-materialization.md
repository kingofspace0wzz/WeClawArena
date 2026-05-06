# Benchmark Materialization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the canonical `benchmark/scenarios/v1.0.0` tree for the balanced difficulty pilot, with resource-enabled scenarios constructed from ASB-backed world packs rather than anonymous resource overlays.

**Architecture:** Use `scripts/orchestrate_benchmark.py` as the non-interactive workflow layer and `scripts/generate_benchmark_scaffold.py` as the materializer. Registered template rows are written through the existing bundle emitter; resource-enabled rows bind a `benchmark/worlds/v1.0.0` user world pack into the template shape before attack injection, which adds ASB profile-source metadata, filesystem/database fixtures, governance bindings, and `construction_manifest` metadata to the GT bundle. The five audit challenge rows remain hand-authored JSON bundles plus generated runtime sidecars. Root and episode-graph index files make the generated dataset countable and auditable.

**Tech Stack:** Python 3.11, pytest, pydantic scenario models, existing generator emitters, existing scenario validator.

## Correction as of 2026-05-05

The 550-variant materialization target is now a pre-calibration scaffold target. The active materialization target is the 680-variant balanced difficulty pilot: 630 main matched variants, 25 hard variants, 20 episode-graph variants, and 5 audit challenge cases. Every main row must carry task schema v0 metadata, designed difficulty tier, source-pattern metadata, and a task-success spec before LLM naturalization or paid simulation.

---

## File Structure

- Modify `scripts/generate_benchmark_scaffold.py` and `scripts/orchestrate_benchmark.py` to add canonical bundle path helpers, full materialization, world-pack binding for resource-enabled rows, benchmark indexes, episode-graph indexes, and audit-challenge bundle emission.
- Modify orchestration / scaffold tests to cover the canonical 680-variant pilot layout, indexes, task schema v0 metadata, and validation of every planned bundle.
- Create or update generated files under `benchmark/scenarios/v1.0.0/` by running the materializer. This includes `main/`, `hard/`, `episode_graphs/`, `audit_challenges/`, resource sidecars, and GT construction metadata.

## Task 1: Lock Canonical Layout Tests

**Files:**
- Modify: `tests/test_scripts/test_generate_benchmark_scaffold.py`

- [x] **Step 1: Add failing layout test**

Add a test that runs:

```python
rc = generate_benchmark_scaffold.main([
    "--materialize-benchmark",
    "--strata",
    "all",
    "--seed",
    "1200",
    "--out",
    str(out),
])
```

Then assert `index.json` reports 680 variants with `main=630`, `hard=25`, `episode_graph=20`, and `audit_challenges=5`. Assert every indexed `bundle_path` has `scenario.json`, `scenario.gt.json`, `docker-compose.yml`, `personas/`, and `mcp/`. For main rows, assert `construction_manifest` includes `task_schema_version`, `designed_difficulty_tier`, `source_pattern`, `benign_task_objective`, and `task_success_spec`.

- [x] **Step 2: Add failing episode-graph test**

Assert `episode_graphs/index.json` lists five graphs and each graph has a `graph.json` file containing exactly four episode bundle paths.

- [x] **Step 3: Add failing validation test**

For every row in `index.json`, run `validate_bundle(out / row["bundle_path"])` and assert the report has no errors. For audit challenge rows, also assert `action_log.json` exists.

- [x] **Step 4: Run red tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_scripts/test_generate_benchmark_scaffold.py -q
```

Expected result: failure because `--materialize-benchmark` and the index files do not exist yet.

## Task 2: Implement Canonical Materializer

**Files:**
- Modify: `scripts/generate_benchmark_scaffold.py`

- [x] **Step 1: Add CLI flag**

Add `--materialize-benchmark` as a third mode. Keep it mutually exclusive with `--dry-run` and `--generate-supported`.

- [x] **Step 2: Add bundle path helper**

Implement a helper with this behavior:

```python
main -> main/<scenario_id>
hard -> hard/<scenario_id>
episode_graph -> episode_graphs/<graph_id>/<scenario_id>
audit_challenges -> audit_challenges/<case_id>
```

- [x] **Step 3: Write registered template rows**

For `main`, `hard`, and `episode_graph`, instantiate the registered template, apply a world pack when the row is resource-enabled, and write a complete bundle to `out / bundle_path`. Apply `inject_attack` after world-pack binding when `attack_type` is set so resource attacks target world-pack resources.

- [x] **Step 4: Write audit challenge rows**

For the five named audit challenge case ids, write `scenario.json`, `scenario.gt.json`, and `action_log.json`. Then generate `docker-compose.yml`, `personas/`, `mcp/`, optional `governance/`, and optional `resources/` sidecars from those JSON files.

- [x] **Step 5: Write indexes**

Write `index.json` at the output root with one row per scenario. Write `episode_graphs/index.json` and one `graph.json` per graph with four episode paths.

- [x] **Step 6: Run green tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_scripts/test_generate_benchmark_scaffold.py -q
```

Expected result: all tests in this file pass.

## Task 3: Materialize Canonical Dataset

**Files:**
- Create/update: `benchmark/scenarios/v1.0.0/**`

- [x] **Step 1: Generate the canonical tree**

Run:

```bash
.venv/bin/python scripts/generate_benchmark_scaffold.py --materialize-benchmark --strata all --seed 1200 --out benchmark/scenarios/v1.0.0
```

- [x] **Step 2: Verify scenario count**

Confirm `benchmark/scenarios/v1.0.0/index.json` reports `scenario_count` as `680` and the expected stratum counts. Confirm `benchmark/scenarios/v1.0.0/build_report.json` reports `generation_status == "GENERATED"`, `construction_mode == "world_pack"`, `realism_status == "worldpack_draft"`, task schema v0 coverage, and `release_ready == false`.

- [x] **Step 3: Verify all bundles**

Run:

```bash
.venv/bin/python -m pytest tests/test_scripts/test_generate_benchmark_scaffold.py -q
.venv/bin/python -m ruff check scripts/generate_benchmark_scaffold.py tests/test_scripts/test_generate_benchmark_scaffold.py
.venv/bin/python -m mypy scripts/generate_benchmark_scaffold.py tests/test_scripts/test_generate_benchmark_scaffold.py
```

Expected result: pytest, ruff, and mypy pass.

## Task 4: Full Regression Check

**Files:**
- No planned file edits.

- [x] **Step 1: Run audit challenge tests**

Run:

```bash
.venv/bin/python -m pytest tests/audit_challenges -q
```

Expected result: governance and resource audit challenge fixtures still pass.

- [x] **Step 2: Run the full suite if time allows**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected result: no regressions beyond known skipped tests.

## Self-Review

- The plan covers canonical layout, materialization, indexes, audit challenge sidecars, and validation.
- There are no placeholder steps.
- The materializer keeps generated template rows separate from hand-authored audit challenge rows.
- Resource-enabled generated rows now carry world-pack construction metadata. The resulting benchmark is generated and ready for annotator review, but it is not release-ready while `realism_status` remains below `human_reviewed`.
