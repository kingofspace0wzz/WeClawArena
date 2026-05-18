# MARBLE Bargaining 24 Owned-Ecosystem Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand MARBLE bargaining to 24 distinct owned-ecosystem base scenarios: 12 `CU-A` tasks and 12 `CM-A` tasks.

**Architecture:** Keep `marble_bargaining` as one family pack, but make task selection cell-aware. The family-level task table exposes all 24 distinct seeds for audits and direct loader tests; the Phase 5 base generator passes `cell_id` so `CU-A-marble_bargaining` materializes the 12 CU seeds and `CM-A-marble_bargaining` materializes the 12 CM seeds. This preserves base IDs such as `CU-A-marble_bargaining__t4` and `CM-A-marble_bargaining__t4` while making those two rows different tasks.

**Tech Stack:** Python dataclasses, Phase 5 family-pack generator, SQLite resource materialization, pytest.

---

### Task 1: Pin The 24-Task Selection Contract

**Files:**
- Modify: `tests/test_generator/test_phase5_task_variants.py`
- Modify: `tests/test_generator/test_marble_bargaining_loader.py`
- Modify: `tests/test_generator/test_phase5_base_generator.py`

- [ ] **Step 1: Add failing tests for family and cell counts**

Add tests asserting:

```python
def test_marble_bargaining_exposes_24_total_distinct_owned_tasks() -> None:
    variants = task_variants_for("marble_bargaining")
    assert len(variants) == 24
    assert len({v.loader_kwargs["transaction_id"] for v in variants}) == 24
    assert len({v.loader_kwargs["resource_profile"] for v in variants}) == 24


def test_marble_bargaining_cell_slices_are_12_distinct_tasks() -> None:
    cu = task_variants_for("marble_bargaining", cell_id="CU-A-marble_bargaining")
    cm = task_variants_for("marble_bargaining", cell_id="CM-A-marble_bargaining")
    assert len(cu) == 12
    assert len(cm) == 12
    assert [v.task_index for v in cu] == list(range(12))
    assert [v.task_index for v in cm] == list(range(12))
    assert cu[0].loader_kwargs["transaction_id"] != cm[0].loader_kwargs["transaction_id"]
    assert cu[0].loader_kwargs["resource_profile"] != cm[0].loader_kwargs["resource_profile"]
```

- [ ] **Step 2: Add a failing base-generator test**

Add a test that generates only bargaining cells and asserts exactly 24 records:

```python
def test_bargaining_cells_materialize_24_cell_specific_tasks(tmp_path: Path) -> None:
    bargaining_cells = tuple(
        cell for cell in all_cells() if cell.family_id == "marble_bargaining"
    )
    records = generate_base_bundles(out_dir=tmp_path, cells=bargaining_cells)
    assert len(records) == 24
    assert {r.cell_id for r in records} == {
        "CU-A-marble_bargaining",
        "CM-A-marble_bargaining",
    }
    assert {r.task_index for r in records if r.cell_id == "CU-A-marble_bargaining"} == set(range(12))
    assert {r.task_index for r in records if r.cell_id == "CM-A-marble_bargaining"} == set(range(12))
    assert len({r.loader_kwargs["transaction_id"] for r in records}) == 24
```

- [ ] **Step 3: Run red tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_generator/test_phase5_task_variants.py tests/test_generator/test_marble_bargaining_loader.py tests/test_generator/test_phase5_base_generator.py -q -k 'bargaining'
```

Expected: failures showing the current variant count is 4 and `task_variants_for` does not accept `cell_id`.

### Task 2: Implement Cell-Aware Seed Selection

**Files:**
- Modify: `clawsocialarena/generator/family_packs/marble_bargaining/bargaining_seed_data.py`
- Modify: `clawsocialarena/generator/phase5_task_variants.py`
- Modify: `clawsocialarena/generator/phase5_base_generator.py`

- [ ] **Step 1: Add seed grouping helpers**

In `bargaining_seed_data.py`, add:

```python
BARGAINING_CU_TASK_SEEDS: tuple[BargainingTaskSeed, ...] = (...)
BARGAINING_CM_TASK_SEEDS: tuple[BargainingTaskSeed, ...] = (...)
BARGAINING_TASK_SEEDS: tuple[BargainingTaskSeed, ...] = (
    *BARGAINING_CU_TASK_SEEDS,
    *BARGAINING_CM_TASK_SEEDS,
)

def bargaining_task_seeds_for_cell(cell_id: str | None) -> tuple[BargainingTaskSeed, ...]:
    if cell_id == "CU-A-marble_bargaining":
        return BARGAINING_CU_TASK_SEEDS
    if cell_id == "CM-A-marble_bargaining":
        return BARGAINING_CM_TASK_SEEDS
    return BARGAINING_TASK_SEEDS
```

- [ ] **Step 2: Add 20 new distinct seeds**

Keep existing `t0-t3` as the CU slice. Add CU `t4-t11` and CM `t0-t11` with distinct transaction IDs, owners, resources, and profiles. Use existing generic schemas and task-specific `terms_json` instructions rather than adding new tool names.

- [ ] **Step 3: Make task variants cell-aware**

Update `task_variants_for` and `task_variant_at` signatures:

```python
def task_variants_for(family_id: str, *, cell_id: str | None = None) -> tuple[TaskVariantSpec, ...]:
    ...

def task_variant_at(family_id: str, task_index: int, *, cell_id: str | None = None) -> TaskVariantSpec:
    return task_variants_for(family_id, cell_id=cell_id)[task_index]
```

For `marble_bargaining`, call `bargaining_task_seeds_for_cell(cell_id)`. For other families, ignore `cell_id`.

- [ ] **Step 4: Update the base generator**

In `generate_base_bundles`, call:

```python
variants_cache[cache_key] = task_variants_for(cell.family_id, cell_id=cell.cell_id)
```

Use a `(family_id, cell_id)` cache key so CU and CM slices do not share one cached tuple.

- [ ] **Step 5: Run green tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_generator/test_phase5_task_variants.py tests/test_generator/test_marble_bargaining_loader.py tests/test_generator/test_phase5_base_generator.py -q -k 'bargaining'
```

Expected: all selected tests pass.

### Task 3: Refresh Active Scenario Reports

**Files:**
- Create: `docs/phase_5/scenarios/bargaining/cu_a/`
- Create: `docs/phase_5/scenarios/bargaining/cm_a/`
- Modify: `docs/phase_5/scenarios/bargaining/README.md`

- [ ] **Step 1: Move active report layout to cell folders**

Create one report per active base scenario:

```text
docs/phase_5/scenarios/bargaining/cu_a/t0_owned_ecosystem_procurement.md
...
docs/phase_5/scenarios/bargaining/cu_a/t11_<slug>.md
docs/phase_5/scenarios/bargaining/cm_a/t0_<slug>.md
...
docs/phase_5/scenarios/bargaining/cm_a/t11_<slug>.md
```

- [ ] **Step 2: Update the README index**

The README must state:

```text
Current target: 24 distinct owned-ecosystem bargaining base scenarios.
CU-A rows: 12
CM-A rows: 12
Main attack-mode rows after five modes: 120
```

- [ ] **Step 3: Preserve old top-level reports as archive history**

Move prior top-level `t0-t3` reports to an archive folder if they no longer correspond to the new cell-specific grid.

### Task 4: Materialize The 24 Bargaining Bundles

**Files:**
- Generated: `benchmark/phase5/scaffold/CU-A-marble_bargaining/task0` through `task11`
- Generated: `benchmark/phase5/scaffold/CM-A-marble_bargaining/task0` through `task11`
- Generated: `benchmark/scenarios/v2.0.0/bargaining/`

- [ ] **Step 1: Run focused scaffold generation for bargaining cells**

Run the project command that regenerates bargaining bundles or use the existing Phase 5 generator with bargaining cells only. The output must include 24 base bundle directories and 120 variants after attack modes.

- [ ] **Step 2: Refresh the published bargaining store**

Run the existing bargaining store refresh/publish path so `benchmark/scenarios/v2.0.0/bargaining` contains all 24 base IDs.

- [ ] **Step 3: Inspect the published manifest**

Assert:

```text
base IDs: CU-A-marble_bargaining__t0..t11 and CM-A-marble_bargaining__t0..t11
no_attacker rows: 24
all five modes: 120
```

### Task 5: Verification

**Files:**
- Test: `tests/test_generator/test_phase5_task_variants.py`
- Test: `tests/test_generator/test_marble_bargaining_loader.py`
- Test: `tests/test_generator/test_marble_bargaining_materialize.py`
- Test: `tests/test_generator/test_phase5_base_generator.py`
- Test: `tests/test_scripts/test_refresh_bargaining_store.py`

- [ ] **Step 1: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_generator/test_phase5_task_variants.py tests/test_generator/test_marble_bargaining_loader.py tests/test_generator/test_marble_bargaining_materialize.py tests/test_generator/test_phase5_base_generator.py tests/test_scripts/test_refresh_bargaining_store.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Compile edited Python files**

Run:

```bash
.venv/bin/python -m py_compile clawsocialarena/generator/family_packs/marble_bargaining/bargaining_seed_data.py clawsocialarena/generator/phase5_task_variants.py clawsocialarena/generator/phase5_base_generator.py
```

Expected: exit code 0.

- [ ] **Step 3: Check formatting hazards**

Run:

```bash
rg -n "[[:blank:]]$" clawsocialarena/generator/family_packs/marble_bargaining/bargaining_seed_data.py clawsocialarena/generator/phase5_task_variants.py clawsocialarena/generator/phase5_base_generator.py docs/phase_5/scenarios/bargaining docs/superpowers/plans/bargaining/2026-05-15-marble-bargaining-24-owned-ecosystem-tasks.md
git diff --check -- clawsocialarena/generator/family_packs/marble_bargaining/bargaining_seed_data.py clawsocialarena/generator/phase5_task_variants.py clawsocialarena/generator/phase5_base_generator.py tests/test_generator/test_phase5_task_variants.py tests/test_generator/test_marble_bargaining_loader.py tests/test_generator/test_phase5_base_generator.py docs/phase_5/scenarios/bargaining docs/superpowers/plans/bargaining/2026-05-15-marble-bargaining-24-owned-ecosystem-tasks.md
```

Expected: no output from either command.
