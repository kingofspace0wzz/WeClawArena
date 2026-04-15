# Phase 2 — Summary

Annotated summary of `phase-2-codex-raw.md`. Phase 2 delivered the Social Auditability Framework scoring layer through 5 tasks (commits `638ea02` → `1b65e51`). 72/72 tests green.

## Codex findings (8 items; see `phase-2-codex-raw.md` for full text)

### Critical / bug

1. **Recoverability — BUG.** Only compares `(agent_id, action_id)` sets. Tampered payload under same ID → still scores 1.0. Primary-only injected actions → score 1.0.
2. **Policy Checkability — BUG.** `gt.policies` never loaded into scorer's registry — dimension silently defaults to 1.0 regardless of declared policies. Also required-fields presence checked across records rather than per-record.
3. **Attribution DAG — BUG.** `EvalRunner.evaluate` hardcodes `produced_dag={"nodes":[],"edges":[]}`. Any non-empty GT DAG scores 0.0.
5. **Phase-Scoped Policy — BUG.** `decidable_and_satisfied = True` starter never flips when zero records in the phase. Missing-field treated as hard failure instead of "not decidable."
8. **MVP fixture change — BUG.** `integrity_requirements` emptied to make MVP score 1.0, hiding the HASH_CHAINED-vs-threshold tension.

### Concern

4. **Evidence Integrity — CONCERN.** Formula matches spec but HASH_CHAINED records scoring only 0.75 → below the 0.80 pass threshold. Intended spec behavior for unsigned runs, but MVP test assertion "all dims == 1.0" created a false conflict.
7. **EvalRunner purity — CONCERN.** Registry is hidden constructor state; `gt.policies` not used.

### OK

6. **SAFScorer geometric mean — OK.** Numerically stable to 1e-10; zero short-circuit correct.

## Phase 2.5 remediation (4 commits)

- `c992833` strengthen Recoverability to content-hash comparison → fixes #1
- `80ab324` EvalRunner builds PolicyRegistry from gt.policies via PolicyCatalog → fixes #2, #7
- `9f87f37` phase-scoped scorer separates decidability/satisfaction + vacuous-in-phase handling → fixes #5
- `a080f11` restore MVP integrity_requirements; evidence_integrity=0.75 under baseline → fixes #4, #8

## Status after Phase 2.5 (per `phase-2.5-codex-raw.md`)

- RESOLVED: #4, #5, #6, #7, #8
- PARTIALLY RESOLVED: #1 (primary-only extras still ignored — per spec formula), #2 (per-record decidability fix still needed — done in Phase 3 Task 3.0 as commit `686a1c0`)
- NOT RESOLVED: #3 (Attribution DAG — resolved in Phase 3 Task 3.2 as commit `f1ff8f0`)

All bugs closed by end of Phase 3.0.
