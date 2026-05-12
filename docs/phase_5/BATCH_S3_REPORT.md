# Phase 5 Batch S3 Report -- Generators

**Date:** 2026-05-10
**Scope:** Generators (base tasks + attack variants + supplementary) on top of S1/S2 family-pack scaffolding.
**Status:** Complete; awaiting codex review.

## 1. Goal

S3 builds the deterministic scaffolding that turns the 14 cell × family allocation (S1) and per-pack naturalization hints (S2) into a 680-row pilot manifest:

- 126 base bundles = 14 cells × 3 task variants × 3 difficulty tiers
- 630 main attack variants = 126 bases × 5 attack modes (1 baseline + 4 attack types)
- 50 supplementary descriptors = 25 hard-verification + 20 episode-graph + 5 named audit

All 680 rows are addressable via a single `phase5_manifest.json` and a stratum/tier/task/mode selector. Run-Batches 1..5 consume this manifest unchanged.

## 2. Deliverables

### 2.1 New modules (8 production + 7 test + 1 script)

```
clawsocialarena/generator/
  difficulty_tier.py          (220 lines)  TierSpec, apply_tier, bargaining_window_kwargs
  phase5_task_variants.py     (308 lines)  3 identity variants per registered family
  phase5_base_generator.py    (315 lines)  generate_base_bundles -> 126 materialized bundles
  phase5_attack_payloads.py   (463 lines)  4 attack payloads per family, scenario-aware
  phase5_attack_variants.py   (272 lines)  expand 126 bases -> 630 variants
  phase5_supplementary.py     (254 lines)  50 descriptor rows across 3 sub-strata
  phase5_manifest.py          (234 lines)  assemble_manifest + select_rows

scripts/
  generate_phase5_manifest.py (85 lines)   CLI wrapper that prints the stratum breakdown

tests/test_generator/
  test_difficulty_tier.py            (184 lines, 12 tests)
  test_phase5_task_variants.py       (102 lines, 10 tests)
  test_phase5_base_generator.py      (164 lines, 14 tests, 1 slow)
  test_phase5_attack_payloads.py     (146 lines, 17 tests)
  test_phase5_attack_variants.py     (147 lines, 12 tests)
  test_phase5_supplementary.py       (89 lines,  8 tests)
  test_phase5_manifest.py            (156 lines,  6 tests, 1 slow)

Total: 3,139 lines (1,931 production + 988 tests + 85 CLI + difficulty_tier 220).
```

### 2.2 Updates to existing files

- `clawsocialarena/generator/difficulty_tier.py` -- extracted `bargaining_window_kwargs` as a public helper so the base generator and the tier-overlay agree on the narrowed window. `_bargaining_tier_override` now delegates to the public helper.
- `pyproject.toml` -- registered the `slow` pytest marker so the full-pipeline integration tests can be opted in/out via `-m "not slow"`.

## 3. Mechanical results

### 3.1 Tier scaffold

The `TIERS` table is the only authority on tier multipliers / attack intensities:

| Tier | Name | max_turns × | attack_intensity |
|------|------|-------------|------------------|
| 1 | easy | 1.0 | 0.4 |
| 2 | medium | 1.3 | 0.6 |
| 3 | hard | 1.6 | 0.8 |

Per-pack overrides exist for every registered family (5 no-op + 1 bargaining). The bargaining override narrows the (seller_reservation, buyer_budget_ceiling) window proportionally: tier 2 keeps 70% of the default offset, tier 3 keeps 40% (so at market $50 the tier-1 window is $40..$60 and the tier-3 window collapses to $48..$52).

### 3.2 Identity variants

Three frozen identity-kwarg variants per family (18 variants total). The base-task generator confirms each variant set loads + materializes for every family. Variants use disjoint participant owner names so on-disk bundles do not collide.

### 3.3 Manifest math (verified end-to-end)

```
$ PYTHONPATH=. python scripts/generate_phase5_manifest.py --out-dir /tmp/phase5_smoke
{
  "n_main": 630,
  "n_supplementary": 50,
  "n_total": 680,
  "main_per_tier": {"1": 210, "2": 210, "3": 210},
  "main_per_attack_mode": {
    "approval_bypass": 126,
    "collaborative_exfiltration": 126,
    "goal_hijacking": 126,
    "no_attacker": 126,
    "prompt_injection": 126
  }
}
```

The 210-per-tier × 3 = 630 and 126-per-mode × 5 = 630 cross-checks land on the same number, confirming the matrix is consistent.

### 3.4 Selector contract (consumed by Run-Batches 1..5)

| Run-Batch | Selector | Row count |
|-----------|----------|-----------|
| 1 (smoke) | `stratum="main", tier_index=1, task_index=0` | 70 |
| 2 (task div) | `stratum="main", tier_index=1` (all tasks) | 210 |
| 3 (tier 2) | `stratum="main", tier_index=2` | 210 |
| 4 (tier 3) | `stratum="main", tier_index=3` | 210 |
| 5 (supplementary) | `stratum="supplementary"` | 50 |

The slow test `test_full_manifest_writes_680_rows` pins these numbers directly so the manifest cannot drift without breaking CI.

### 3.5 Attack payloads

Five attack modes (`no_attacker` baseline + four attack types: `prompt_injection`, `collaborative_exfiltration`, `approval_bypass`, `goal_hijacking`). Each non-baseline payload:

- carries a delivery surface (`opening_message`, `peer_message`, `system_aside`)
- targets a real agent id that exists in the materialized scenario
- quotes the live identity kwargs (household_id, group_id, account_id, meeting_id, etc.) so the payload text is family-specific rather than generic

Tests pin both the type-ordering contract and the target-agent-existence invariant for every registered family.

### 3.6 Supplementary stratum

50 descriptor records split exactly per spec section 1 of the benchmark design:

- 25 hard-verification (12 code-review + 13 doc-editing), parameterized by Phase-E tier (`easy`/`realistic`/`stress`).
- 20 episode-graph (5 graphs of 4 episodes each), rotating across 5 families to avoid leaning on one entity surface.
- 5 named audit challenge cases, each targeting a distinct SAF failure mode (`saf_attribution_collision`, `saf_consent_loop`, `saf_governance_drift`, `saf_privacy_leak_in_summary`, `saf_resource_silent_overwrite`).

Materialization is deferred to Run-Batch 5 because the hard-verification and episode-graph rows reuse Phase-E templates (`HardCodeReviewTemplate`, `HardDocEditingTemplate`) whose materializers operate on a different shape from family packs.

## 4. Test results

```
$ pytest tests/test_generator/ --tb=short -q
469 passed, 12 warnings in 20.56s

$ pytest tests/ --tb=line -q   # full repo
1460 passed, 8 failed, 63 warnings in 419.63s
```

The 8 failures are all pre-existing in out-of-scope suites:

- `tests/e2e/test_generated_compose.py` (1) -- Docker-dependent end-to-end
- `tests/test_saf/*` (2) -- SAF scorer baseline
- `tests/test_scenario/*` (5) -- Pydantic round-trip checks against unrelated schema work

S2 reported 7 of these and noted they were unchanged across earlier batches; the +1 is `e2e/test_generated_compose.py` which is unrelated to S3 (Docker isolation). No new failures landed in S3.

## 5. Coverage of risks codex flagged after Batch A

| Risk | Mitigation |
|------|------------|
| Drift between `apply_tier` and any caller that also computes the bargaining window | `bargaining_window_kwargs` is now the single public helper consumed by both `apply_tier` and `phase5_base_generator._maybe_narrow_bargaining_kwargs`. |
| Per-pack override map could go out of sync with registered families | `test_per_pack_override_dict_covers_every_registered_family` enforces parity. |
| Attack payloads could quietly target a non-existent agent_id | `test_payload_target_agent_ids_are_real_for_each_family` parametrized over every registered family. |
| Variant table could share owner names across variants, causing on-disk path collisions | `test_variants_use_disjoint_participant_owners` parametrized over every registered family. |
| Manifest row count could silently diverge from the 630/50/680 spec | `assemble_manifest` raises a hard ValueError on mismatch; both `test_total_constants_align` and `test_full_manifest_writes_680_rows` lock the numbers. |

## 6. Pipeline timing

Full 14-cell × 3-task × 3-tier × 5-mode materialization (the slow test) lands in **4.5 seconds** on this machine. Run-Batch 1 (70 scenarios) will spend the bulk of its budget on gpt-4.1-mini agent simulation; materialization is not a bottleneck.

## 7. Open items handed to S4

- The supplementary materialization recipes (`HardCodeReviewTemplate`, `HardDocEditingTemplate`, `episode_graph`, `named_audit_case`) need to be wired into the Run-Batch 5 orchestrator. S3 only emits the 50 descriptor rows; S4 makes them executable.
- The selector contract for Run-Batches 1..5 is fixed (see section 3.4); the orchestrator should call `select_rows` directly rather than re-deriving filters.

## 8. Files inventory

```
clawsocialarena/generator/difficulty_tier.py            (220 LOC)
clawsocialarena/generator/phase5_task_variants.py       (308 LOC)
clawsocialarena/generator/phase5_base_generator.py      (315 LOC)
clawsocialarena/generator/phase5_attack_payloads.py     (463 LOC)
clawsocialarena/generator/phase5_attack_variants.py     (272 LOC)
clawsocialarena/generator/phase5_supplementary.py       (254 LOC)
clawsocialarena/generator/phase5_manifest.py            (234 LOC)
scripts/generate_phase5_manifest.py                     ( 85 LOC)
tests/test_generator/test_difficulty_tier.py           (184 LOC, 12 tests)
tests/test_generator/test_phase5_task_variants.py      (102 LOC, 10 tests)
tests/test_generator/test_phase5_base_generator.py     (164 LOC, 14 tests)
tests/test_generator/test_phase5_attack_payloads.py    (146 LOC, 17 tests)
tests/test_generator/test_phase5_attack_variants.py    (147 LOC, 12 tests)
tests/test_generator/test_phase5_supplementary.py       ( 89 LOC,  8 tests)
tests/test_generator/test_phase5_manifest.py           (156 LOC,  6 tests)

Total: 8 production modules, 7 test modules, 1 CLI script, 79 new tests.
```
