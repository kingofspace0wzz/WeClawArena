# ClawSocialArena Documentation Index

Use this file to decide what to read first. Older files remain in the repository for audit history, but current execution should start from the files marked current. Specs earlier than 2026-05-06 are historical and should not be used as active Phase 5 design references.

## Current Entry Points

| Need | Read |
|---|---|
| Current branch, batch, and benchmark status | `docs/project_status.md` |
| Benchmark data layout, metrics, and construction QC reports | `docs/benchmark_dataset_guide.md` |
| Runtime and SAF design | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-runtime-saf-design.md` |
| Benchmark construction design | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-benchmark-design.md` |
| Experimental design | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-experimental-design.md` |
| Attack vector and stress-attack design | `docs/superpowers/specs/2026-05-08-clawsocialarena-v2-attack-vector-design.md` |
| MARBLE bargaining current design | `docs/superpowers/specs/bargaining/README.md` |
| SWE-bench workspace stress attacks | `docs/superpowers/specs/2026-05-14-swebench-workspace-stress-attack-redesign.md` |
| Topology design (coordination modes, agent_graph, validation) | `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-topology-design.md` |
| Task-contract design (evaluation_criteria, reward_basis, predicate registry) | `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-task-contract-design.md` |
| Family pack design (six families, allocation table, per-family detail) | `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md` |

## Current Implementation Plans

| Plan | Role |
|---|---|
| `docs/superpowers/plans/2026-05-05-task-difficulty-success-calibration.md` | Current task-difficulty and stricter task-success plan. |
| `docs/superpowers/plans/2026-05-02-benchmark-materialization.md` | Current 680-variant scaffold materialization plan. |
| `docs/superpowers/plans/2026-05-02-benchmark-orchestration.md` | Current scaffold orchestration plan. |
| `docs/superpowers/plans/2026-05-02-llm-naturalization-batch-pipeline.md` | Current LLM naturalization and Docker simulation batch plan. |
| `docs/superpowers/plans/2026-05-02-resource-coverage-matrix.md` | Current resource-coverage plan. |
| `docs/superpowers/plans/bargaining/README.md` | Bargaining plan index. Existing plans are historical until a new owned-ecosystem implementation plan is written. |
| `docs/superpowers/plans/2026-05-15-swebench-workspace-stress-asr.md` | Current SWE-bench workspace stress ASR implementation plan. |
| `docs/superpowers/plans/2026-05-02-user-world-pack-scenario.md` | Historical plan superseded by bundle-local scenario-world and family-pack specs; do not use for Phase 5 execution. |

## Architecture References

| Spec | Role |
|---|---|
| `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-runtime-saf-design.md` | Current harms-first motivation, threat model, runtime architecture, policy-hook, MSWM, and SAF reference. |
| `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-benchmark-design.md` | Current benchmark construction, scenario grid, attack-mode, bundle-local scenario-world, task-difficulty, and construction batch-gate reference. |
| `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-experimental-design.md` | Current experimental protocol, run-validation, deterministic and LLM-judge metric layers, batch-report, aggregation, and compute-planning reference. |
| `docs/superpowers/specs/2026-05-08-clawsocialarena-v2-attack-vector-design.md` | Current attack-mode contract, stress-attack recipes, filesystem and database attack surfaces, attack-stage metrics, and calibration targets. |
| `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-topology-design.md` | Current topology and scenario-composition reference. Coordination modes adopted from MARBLE, agent_graph schema, validation rules, construction pipeline changes. Replaces per-category template references in earlier specs. |
| `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-task-contract-design.md` | Current task-contract shape and evaluation pipeline reference. evaluation_criteria schema and reward_basis enum adopted from tau2-bench, predicate registry, eval/runner.py Stage 4 dispatch, scenario.gt.json migration. |
| `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md` | Current six-family pack reference. Per-family external source, multi-partying approach, fixtures, evaluation_criteria shape, phase schedule, governance manifest sourcing, and attack-recipe payloads. Includes the 14-cell allocation table that preserves the 680-variant pilot math. |
| `docs/superpowers/specs/bargaining/README.md` | Bargaining spec index. Start here for bargaining work. |
| `docs/superpowers/specs/bargaining/2026-05-16-marble-bargaining-task-construction.md` | Current MARBLE bargaining task construction. Defines the 24 owned-ecosystem base tasks, 120-row grid, Docker-backed runtime contract, tools, and cap-36 rule. |
| `docs/superpowers/specs/bargaining/2026-05-16-marble-bargaining-attack-vectors.md` | Current MARBLE bargaining five-mode attack contract and active payload semantics. |
| `docs/superpowers/specs/bargaining/2026-05-16-marble-bargaining-evaluation-metrics.md` | Current MARBLE bargaining metrics. Defines raw TSR, deterministic ASR, SAF fields, and LLM-as-a-judge ASR reporting. |
| `docs/superpowers/specs/bidding/README.md` | Bidding spec index. Start here for `marble_bidding` work. |
| `docs/superpowers/specs/bidding/2026-05-16-marble-bidding-owned-ecosystem-design.md` | Current MARBLE bidding owned-ecosystem design. Keeps bidding separate from bargaining and defines the six-task bidding slice. |
| `docs/superpowers/specs/2026-05-14-swebench-workspace-asr-llm-judge-design.md` | SWE-bench workspace ASR LLM-judge design. Defines workspace evidence packets, per-axis rubrics, baseline labels, and judge/deterministic reporting separation. |
| `docs/superpowers/specs/2026-05-14-swebench-workspace-stress-attack-redesign.md` | SWE-bench workspace stress-attack design. Defines attack surfaces, tactic families, workspace payloads, and stress calibration targets. |
| `docs/superpowers/specs/2026-04-17-clawsocialarena-v2-design.md` | Superseded monolith pointer retained for old links. |
| `docs/superpowers/specs/2026-04-27-mswm-transaction-refactor-design.md` | MSWM tentative-state and transaction design. |
| `docs/superpowers/specs/2026-05-02-user-world-pack-scenario-design.md` | Superseded historical user world-pack draft. Phase 5 uses bundle-local scenario worlds from family packs. |
| `docs/superpowers/specs/2026-05-02-llm-naturalization-batch-pipeline-design.md` | LLM naturalization and batch simulation design. |
| `docs/superpowers/specs/2026-05-05-task-difficulty-success-calibration-design.md` | Superseded historical task-difficulty draft. Current difficulty rules live in the benchmark and experimental specs. |

## Archived Historical Docs

| Old file | Archived copy |
|---|---|
| `docs/design.md` | `docs/archive/superseded/design.md` |
| `docs/plan.md` | `docs/archive/superseded/plan.md` |
| `docs/superpowers/plans/2026-04-17-clawsocialarena-v2.md` | `docs/archive/superseded/superpowers/plans/2026-04-17-clawsocialarena-v2.md` |

The old paths now contain pointer stubs so existing links still resolve.

## Branch Notes

`main` is the current working branch. The `v2-refactor` and `phase-I-governance` branches remain checked out as worktrees under `worktree/`. Treat them as historical/reference branches until a separate branch-cleanup review confirms that no unique useful content remains.
