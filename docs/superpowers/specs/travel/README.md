# Travel Family Specs

Status: current as of 2026-05-18.

Code and data version checked: `main` at the redesign-v2 sweep (`benchmark/phase5/pilot/travel_redesign_v2_20260518/`).

This folder is the compact spec set for the `travel` task family, occupying two cells in the Phase 5 grid: `CU-D-travel` (solo triad, traveler + partner_hotel + corp_travel approver) and `MG-C-travel` (group, organizer + 3 co_travelers + partner_hotel). All 20 base tasks are seeded from TravelBench (ACL 2026) and materialized through the family pack pipeline.

## Spec Map

- [data_construction.md](data_construction.md): how TravelBench rows become CU and MG owned-ecosystem scenarios, including lift rotation, bargaining bounds, MG group budget envelope, and materialized resource layout.
- [task_success_metrics.md](task_success_metrics.md): canonical evaluation channels (actions, env_assertions, communicate_info, nl_assertions), travel predicates, and current TSR results.
- [attack_vector_design.md](attack_vector_design.md): travel-specific security, privacy, governance, and collaboration recipes, including the asymmetry fixes from the 2026-05-17/18 redesign.
- [llm_attack_success_evaluator.md](llm_attack_success_evaluator.md): travel LLM ASR judge schema, per-axis rubric, and reporting rules.

Historical design notes for travel are concentrated in `docs/superpowers/plans/travel/` and the per-task scenario pages under `docs/phase_5/scenarios/travel/`.

## Current Published Data

Published path: `benchmark/scenarios/v2.0.0/travel`.

The v2.0.0 manifest has:

| Item | Count |
|---|---:|
| CU-D-travel base scenarios | 10 |
| MG-C-travel base scenarios | 10 |
| Travel manifest rows | 100 |
| no-attacker rows | 20 |
| attack rows | 80 |
| attack modes per base | 4 |

Attack variants are not stored as fully copied folders; the published store carries base bundles and the runner materializes attack variants at runtime through `clawsocialarena.attacks.runtime_overlay.materialize_runtime_variant` plus the travel-specific mode-local playbook (`clawsocialarena.attacks.stress_recipes.travel_mode_local_playbooks`).

## Current Calibration Snapshot

Latest 100-variant sweep: `benchmark/phase5/pilot/travel_redesign_v2_20260518/` (2026-05-18).

| Metric | Value |
|---|---:|
| rows run | 100 |
| TSR overall | 43% (43/100) — under the <50% gpt-4.1-mini target |
| TSR CU-D-travel | 40% (20/50) |
| TSR MG-C-travel | 46% (23/50) |
| TSR no_attacker per cell | 50% / 50% |
| LLM ASR overall | 71% (across 80 attack rows) |
| Judge errors | 0 |
| Wall time | 51 minutes |

The redesign-v2 sweep resolved the asymmetries from the earlier 100-sweep (where 4 cells had ASR=0% and 4 had ASR>=80%) but over-corrected: 7 of 8 (cell, axis) cells now sit above their target band. See `attack_vector_design.md` for the proposed v3 dials.

## Configuration

The travel family runs under the docker executor with:

- `agent-model = gpt-4.1-mini` (calibration target; ASR bands are anchored to this model class)
- `max-turns = 36` (set high enough that recipe-driven turn-cap failures are attack-attributable, not generic search loops)
- `naturalization_model = none` (TravelBench rows ship with English persona translations; no LLM rewrite is applied)

Judge model: `gpt-5.2` over the post-sweep `BATCH_*_RESULTS.jsonl`.

## Family Reporting Convention

`travel` should use task success (`task_success` per `clawsocialarena.eval.predicates.travel`) as the main utility metric and LLM-ASR (the travel judge) as the attack-success metric. The built-in delta-based `attack_success` field is meaningful only for the collaboration axis; the other three axes are not predicate-distinguishable and should be reported via the LLM judge.
