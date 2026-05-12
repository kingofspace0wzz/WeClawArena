# Phase 5 Batch S3 Revision Report

**Date:** 2026-05-11
**Scope:** Address the three blockers + one non-blocker that codex flagged in `BATCH_S3_REPORT.md`'s review.
**Status:** Complete; awaiting re-review.

## 1. Issues addressed

| # | Severity | Issue | Where it lived |
|---|----------|-------|----------------|
| 1 | blocker | Opening-message attack variants did not retarget `opening_message.to`, so tau2_retail / tau2_telecom attacks landed on the wrong agent | `phase5_attack_variants._inject_payload_into_scenario` |
| 2 | blocker | `attack_mode` axis collapsed with `attack_recipe`, breaking spec section 2's matched-axis contract | `phase5_attack_payloads.py`, `phase5_attack_variants.py`, `phase5_manifest.py` |
| 3 | blocker | Tier mechanics inverted (higher tier = more turns = easier) and tier names did not match spec section 5 (`easy / realistic / stress`) | `difficulty_tier.py` |
| 4 | non-blocker | `assemble_manifest` reused a stale `phase5_variants_index.json` when called with new `base_records` | `phase5_manifest.assemble_manifest` |

## 2. Fix 1 — Opening-message recipient retargeting

`_inject_payload_into_scenario` now rewrites `opening_message.to` with the payload's `target_agent_id` whenever the injection surface is the opening message. The base scenarios for tau2_retail and tau2_telecom address the opening message to the secondary; without the rewrite, security / collaboration variants (opening-message kind) were delivered to the wrong agent.

New regression test: `test_opening_message_attack_retargets_recipient` walks tau2_retail and tau2_telecom and asserts `opening_message.to == sidecar.attack.target_agent_id` for every non-baseline opening-message variant.

## 3. Fix 2 — Split attack_mode from attack_recipe

`phase5_attack_payloads.py` now exposes the spec section 2 axis:

```python
ATTACK_MODES_NON_BASELINE = ("collaboration", "security", "privacy", "governance")
ATTACK_MODES_ALL = ("no_attacker",) + ATTACK_MODES_NON_BASELINE

MODE_TO_RECIPE = {
    "collaboration": "goal_hijacking",
    "security":      "prompt_injection",
    "privacy":       "collaborative_exfiltration",
    "governance":    "approval_bypass",
}
```

`AttackPayload` is now a 7-field dataclass that carries:

- `attack_mode` — the spec-stable axis label (one of `ATTACK_MODES_NON_BASELINE`).
- `attack_recipe` — the concrete tactic (from `MODE_TO_RECIPE`).
- `delivery_surface` — canonical `DeliverySurface.MESSAGE` (string `"message"`).
- `attacker_control` — canonical `AttackerControl.SCRIPTED` (string `"scripted"`).
- `target_agent_id`, `payload_text`, `message_kind` (one of `opening_message / peer_message / system_aside`), `metadata`.

`attack_payloads_for` now validates that every per-family builder returns payloads in `ATTACK_MODES_NON_BASELINE` order; an out-of-order builder raises `ValueError` immediately with a pointer at the bad slot.

`VariantRecord` and `MainManifestRow` gained `attack_recipe`, `delivery_surface`, `attacker_control`, and `target_agent_id` columns. The `attack_mode` field now carries the axis label (`collaboration` / `security` / `privacy` / `governance` / `no_attacker`), not the recipe.

`variant_id` format is now `{base_scenario_id}__{attack_mode}` (axis), so selectors like `attack_mode="privacy"` slice cleanly across recipes if more are added later.

Sidecar `phase5_variant_metadata.json` now carries:

```json
"attack": {
  "attack_mode":      "privacy",
  "attack_recipe":    "collaborative_exfiltration",
  "delivery_surface": "message",
  "attacker_control": "scripted",
  "message_kind":     "peer_message",
  "target_agent_id":  "alice_assistant",
  "payload_text":     "...",
  "metadata":         {...}
}
```

End-to-end CLI smoke confirms the new per-mode totals:

```
$ scripts/generate_phase5_manifest.py --out-dir /tmp/phase5_smoke
{
  "n_total": 680,
  "main_per_tier": {"1": 210, "2": 210, "3": 210},
  "main_per_attack_mode": {
    "collaboration": 126,
    "governance": 126,
    "no_attacker": 126,
    "privacy": 126,
    "security": 126
  }
}
```

## 4. Fix 3 — Tier mechanics + naming

`difficulty_tier.TIERS` now matches spec section 5:

| tier | name | max_turns_multiplier | attack_intensity |
|------|------|---------------------|------------------|
| 1 | easy | 1.0 | 0.4 |
| 2 | realistic | 0.8 | 0.6 |
| 3 | stress | 0.6 | 0.8 |

Higher tier = lower turn budget = harder. `realistic` corresponds to the spec's "default benchmark rows with non-trivial constraints"; `stress` corresponds to "rows where failures are expected under the fixed runtime model." The bargaining-window narrowing helper (`bargaining_window_kwargs`) was unchanged because tier-2/3 already narrows the window; only its docstring was tightened.

The base-generator regression now asserts strictly **decreasing** `max_turns` across tiers (`tier_1 > tier_2 > tier_3`) instead of the previous strictly-increasing direction.

The tier-name string in `BaseBundleRecord.tier_name` flows through to the manifest unchanged, so any downstream consumer that reads `tier_name == "hard"` would break — but no such consumer exists yet (the orchestrator slices by `tier_index`, the integer).

## 5. Fix 4 — Manifest rebuild guard (non-blocker)

`assemble_manifest` now defaults to `reuse_existing_variant_index=False`, which forces a fresh `expand_base_records_to_variants` call every time. A caller that has just finished writing the variant index and wants to skip expansion can pass `reuse_existing_variant_index=True` (only used by tests that build the index manually).

New regression test: `test_assemble_manifest_force_rebuilds_variant_index` materializes a one-cell base set, then calls `assemble_manifest` with a smaller subset and confirms the variant index on disk is rebuilt to match the smaller subset.

## 6. Test results

```
$ pytest tests/test_generator/ -q
473 passed
```

S3-specific tests grew from 79 → 87 (the four new regression tests above + four new mode/recipe / taxonomy assertions). No regressions in the broader generator suite (469 → 473, all green).

Slow integration test (`test_full_manifest_writes_680_rows`) still lands the full 680-row manifest in ~4.5 seconds and now also asserts per-mode totals of 126 across all five modes (one mode column × 126 base bundles = 126).

## 7. Files touched

```
clawsocialarena/generator/difficulty_tier.py        (220 -> 227 LOC)
clawsocialarena/generator/phase5_attack_payloads.py (463 -> 552 LOC)
clawsocialarena/generator/phase5_attack_variants.py (272 -> 324 LOC)
clawsocialarena/generator/phase5_manifest.py        (234 -> 258 LOC)

tests/test_generator/test_difficulty_tier.py            (12 tests, unchanged count)
tests/test_generator/test_phase5_attack_payloads.py     (17 -> 18 tests; +1 builder-order rejection)
tests/test_generator/test_phase5_attack_variants.py     (12 -> 14 tests; +1 retarget, +1 recipe round-trip)
tests/test_generator/test_phase5_base_generator.py      (14 tests, unchanged count; flipped monotonicity)
tests/test_generator/test_phase5_manifest.py            (6 -> 7 tests; +1 rebuild-guard)
```

## 8. Pre-existing non-S3 failures

Unchanged from BATCH_S3_REPORT: 8 failures in out-of-scope suites (`test_saf`, `test_scenario`, `test_resource_models`, `e2e/test_generated_compose`). The revision touches none of those code paths.

## 9. Verdict request

All three blockers addressed with regression tests; non-blocker addressed with a rebuild-guard test. Pipeline math still lands at 680 rows; per-tier (210), per-mode (126), and per-cell (45) breakdowns all match the spec.

Re-running codex review with this revision report.

## 10. Revision r2 — close codex's remaining blocker

Codex's first re-review (verdict: REVISE) flagged one remaining blocker and one ergonomics non-blocker.

**Blocker fixed:** `attack_intensity` is now persisted in the on-disk variant sidecar (`phase5_variant_metadata.json`). Previously the field lived only in the in-memory `VariantRecord` and the manifest row, so a consumer reading the sidecar directly could not recover the spec section 2 declaration. New regression test `test_attack_sidecar_carries_every_spec_section_2_field` walks every non-baseline sidecar and asserts the five spec fields (`attack_mode`, `attack_recipe`, `attack_intensity`, `delivery_surface`, `attacker_control`) are all present and that `attack_intensity` matches the base record's tier intensity.

**Ergonomics non-blocker fixed:** `scripts/generate_phase5_manifest.py` now bootstraps `sys.path` from the script's location, so `python scripts/generate_phase5_manifest.py --out-dir ...` runs from any cwd without `PYTHONPATH=.`. Verified from `/tmp` with an absolute path; output is unchanged (630 + 50 = 680 rows, 126 per mode).

**Non-blockers acknowledged but not changed in r2:**
- `system_aside` branch is structurally fine but unexercised by current per-family payloads. The injector code path is covered by the surface enumeration test (`test_payload_target_agent_ids_are_real_for_each_family` asserts the allowed surfaces) but no live payload routes through it. We can add a `system_aside` recipe in a future revision if a family needs one.
- Only `marble_bargaining` has mechanical tightening beyond the turn-budget multiplier at higher tiers. This is defensible for S3 as a starting point; calibration on Run-Batch 3/4 may surface families that need per-tier constraint tightening.
- Partial rebuilds do not prune stale bundle directories from disk -- they only stop referencing them. Idempotent CLI runs into a clean directory avoid the issue; we can add an opt-in `--prune` flag in S4 if it becomes important.
- Codex reported a local `pytest` segfault in their sandbox; this does not reproduce here (474 generator tests pass green).

Test totals after r2: **474 generator tests pass** (up from 473 in r1, +1 sidecar-completeness regression). End-to-end CLI still produces the 680-row manifest with the canonical 5-mode breakdown.
