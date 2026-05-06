# Resource Coverage Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand simulated filesystem and personal database resources from a narrow `CU/scheduling` slice to all non-audit-challenge benchmark variants.

**Architecture:** Keep task templates focused on their social/task structure and add deterministic world-pack resources in the benchmark materializer. Main, hard, and episode-graph variants receive file/SQLite fixtures, resource manifests, and per-agent MCP tool access before bundle emission. The five named audit challenge cases remain hand-authored.

**Tech Stack:** Python 3.11, pytest, existing `TemplateShape`, existing bundle writer, scenario validator, deterministic benchmark materializer.

## Correction as of 2026-05-05

The original 545-resource-row matrix belongs to the 550-variant pre-calibration scaffold. The current balanced difficulty pilot has 675 resource-backed variants: 630 main variants, 25 hard variants, and 20 episode-graph variants. The five named audit challenge cases remain hand-authored and are not required to use the world-pack resource matrix.

---

## Resource Coverage Matrix

The balanced difficulty pilot should contain 675 resource-enabled variants:

| Stratum | Category | Family | Count | Source |
|---|---|---:|---:|---|
| main | CU | scheduling | 45 | world-pack resources |
| main | MC | scheduling | 45 | world-pack resources |
| main | AM | scheduling | 45 | world-pack resources |
| main | CD | consensus | 45 | world-pack resources |
| main | MG | consensus | 45 | world-pack resources |
| main | HS | consensus | 45 | world-pack resources |
| main | CM | consensus | 45 | world-pack resources |
| main | CD | inference | 45 | world-pack resources |
| main | MC | inference | 45 | world-pack resources |
| main | AM | inference | 45 | world-pack resources |
| main | CU | coalition | 45 | world-pack resources |
| main | MG | coalition | 45 | world-pack resources |
| main | HS | coalition | 45 | world-pack resources |
| main | CM | coalition | 45 | world-pack resources |
| hard | CU | code_review | 12 | world-pack resources |
| hard | MC | doc_editing | 13 | world-pack resources |
| episode_graph | CD | inference | 4 | world-pack resources |
| episode_graph | CU | scheduling | 4 | world-pack resources |
| episode_graph | MG | consensus | 4 | world-pack resources |
| episode_graph | HS | coalition | 4 | world-pack resources |
| episode_graph | AM | inference | 4 | world-pack resources |

This gives `main=630`, `hard=25`, `episode_graph=20`, and `audit_challenges=0` inside the 680-variant balanced difficulty pilot, for 675 resource-enabled variants total. The existing three resource audit challenge fixtures stay in `tests/fixtures/resource_audit_challenges/` and remain regression tests, rather than changing the five named audit challenge rows.

## Task 1: Lock Coverage Tests

**Files:**
- Modify: `tests/test_scripts/test_generate_benchmark_scaffold.py`

- [x] **Step 1: Add a failing matrix test**

Add a test that materializes `--strata all`, loads `index.json`, scans each `scenario.gt.json`, and asserts exactly 675 rows have a non-empty `resource_manifest`.

- [x] **Step 2: Assert stratum and cell counts**

The test must assert:

```python
Counter(row["stratum"] for row in resource_rows) == {
    "main": 630,
    "hard": 25,
    "episode_graph": 20,
}
Counter((row["stratum"], row["category"], row["family"]) for row in resource_rows) == {
    ("main", "CU", "scheduling"): 45,
    ("main", "MC", "scheduling"): 45,
    ("main", "AM", "scheduling"): 45,
    ("main", "CD", "consensus"): 45,
    ("main", "MG", "consensus"): 45,
    ("main", "HS", "consensus"): 45,
    ("main", "CM", "consensus"): 45,
    ("main", "CD", "inference"): 45,
    ("main", "MC", "inference"): 45,
    ("main", "AM", "inference"): 45,
    ("main", "CU", "coalition"): 45,
    ("main", "MG", "coalition"): 45,
    ("main", "HS", "coalition"): 45,
    ("main", "CM", "coalition"): 45,
    ("hard", "CU", "code_review"): 12,
    ("hard", "MC", "doc_editing"): 13,
    ("episode_graph", "CD", "inference"): 4,
    ("episode_graph", "CU", "scheduling"): 4,
    ("episode_graph", "MG", "consensus"): 4,
    ("episode_graph", "HS", "coalition"): 4,
    ("episode_graph", "AM", "inference"): 4,
}
```

- [x] **Step 3: Assert resources are runnable**

For every resource-enabled row, assert `resources/manifest.json` exists, every declared resource path exists, `mcp_tool_manifest` includes the declared resource operations, and at least one persona tool list includes `fs.read` and `db.query`.

- [x] **Step 4: Run red tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_scripts/test_generate_benchmark_scaffold.py -q
```

Expected result: failure if the canonical materializer produces fewer than 675 resource-enabled variants.

## Task 2: Implement Resource Overlay

**Files:**
- Create: `clawsocialarena/generator/resource_overlays.py`
- Modify: `scripts/generate_benchmark_scaffold.py`

- [x] **Step 1: Create overlay helper**

Create `apply_resource_overlay(shape, profile_id)` that returns a copied `TemplateShape` with a deterministic file resource, SQLite DB resource, fixtures, and resource tool access added to each agent.

- [x] **Step 2: Preserve native resources**

If a shape already has a non-empty `resource_manifest`, do not replace it.

- [x] **Step 3: Add matrix selection**

In `scripts/generate_benchmark_scaffold.py`, define matrix limits for the non-native cells:

```python
{
    ("main", "MC", "scheduling"): 6,
    ("main", "MG", "consensus"): 9,
    ("hard", "CU", "code_review"): 4,
    ("hard", "MC", "doc_editing"): 3,
    ("episode_graph", "HS", "coalition"): 4,
}
```

Apply the world-pack resources to every non-audit-challenge variant in deterministic plan order.

- [x] **Step 4: Run green tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_scripts/test_generate_benchmark_scaffold.py -q
```

Expected result: the new matrix test passes, and all previous materialization tests still pass.

## Task 3: Regenerate Canonical Data

**Files:**
- Update: `benchmark/scenarios/v1.0.0/**`

- [x] **Step 1: Regenerate benchmark**

Run:

```bash
.venv/bin/python scripts/generate_benchmark_scaffold.py --materialize-benchmark --strata all --seed 1200 --out benchmark/scenarios/v1.0.0
```

- [x] **Step 2: Verify generated resource counts**

Run a script over `benchmark/scenarios/v1.0.0/index.json` and assert the matrix counts above.

- [x] **Step 3: Verify generated bundles**

Run:

```bash
.venv/bin/python -m pytest tests/test_scripts/test_generate_benchmark_scaffold.py tests/audit_challenges -q
.venv/bin/python -m ruff check scripts/generate_benchmark_scaffold.py tests/test_scripts/test_generate_benchmark_scaffold.py clawsocialarena/generator/resource_overlays.py
.venv/bin/python -m mypy scripts/generate_benchmark_scaffold.py tests/test_scripts/test_generate_benchmark_scaffold.py clawsocialarena/generator/resource_overlays.py
```

Expected result: all commands pass.

## Task 4: Full Regression Check

**Files:**
- No planned edits.

- [x] **Step 1: Run full suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected result: no regressions beyond known skipped tests.

## Self-Review

- The matrix covers all 675 non-audit-challenge variants and does not alter the 680-variant balanced difficulty pilot contract.
- The overlay avoids broad template duplication.
- The tests enforce count, placement, resource files, MCP tool contracts, and persona access.
