# ClawSocialArena Documentation Index

Use this file to decide what to read first. Current execution should start from the files listed here. Older specs remain for audit history, but they are not active unless a current file cites them.

## Current Entry Points

| Need | Read |
|---|---|
| Current branch, store, and benchmark status | `docs/project_status.md` |
| Bedrock multi-model v2.0.0 sweep launcher (4 scenarios x 2 Claude models in 8 screens) | `docs/phase_5/bedrock_sweep_runbook.md` |
| Benchmark data layout and inspection guide | `docs/benchmark_dataset_guide.md` |
| Runtime, policy hooks, MSWM, and SAF | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-runtime-saf-design.md` |
| Benchmark construction | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-benchmark-design.md` |
| Evaluation and reporting | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-experimental-design.md` |
| Attack layer | `docs/superpowers/specs/2026-05-08-clawsocialarena-v2-attack-vector-design.md` |

## Current Domain Specs

| Domain | Start here | Current detail files |
|---|---|---|
| `marble_bargaining` | `docs/superpowers/specs/bargaining/README.md` | `docs/superpowers/specs/bargaining/2026-05-16-marble-bargaining-task-construction.md`, `docs/superpowers/specs/bargaining/2026-05-16-marble-bargaining-attack-vectors.md`, `docs/superpowers/specs/bargaining/2026-05-16-marble-bargaining-evaluation-metrics.md` |
| `marble_bidding` | `docs/superpowers/specs/bidding/README.md` | `docs/superpowers/specs/bidding/2026-05-16-marble-bidding-owned-ecosystem-design.md` |
| `travel` | `docs/superpowers/specs/travel/README.md` | `docs/superpowers/specs/travel/data_construction.md`, `docs/superpowers/specs/travel/task_success_metrics.md`, `docs/superpowers/specs/travel/attack_vector_design.md`, `docs/superpowers/specs/travel/llm_attack_success_evaluator.md` |
| `swebench_workspace` | `docs/superpowers/specs/swebench_workspace/README.md` | `docs/superpowers/specs/swebench_workspace/data_construction.md`, `docs/superpowers/specs/swebench_workspace/task_success_metrics.md`, `docs/superpowers/specs/swebench_workspace/attack_vector_design.md`, `docs/superpowers/specs/swebench_workspace/llm_attack_success_evaluator.md`, `docs/superpowers/specs/swebench_workspace/owned_ecosystem_enrichment_design.md` |
| `tau2_retail` | `docs/superpowers/specs/retail/README.md` | Current retail domain notes. |

## Current Plans

| Plan | Role |
|---|---|
| `docs/superpowers/plans/bargaining/README.md` | Bargaining and bidding plan index; older plans are historical unless a current spec cites them. |
| `docs/superpowers/plans/travel/README.md` | Travel plan index. |
| `docs/superpowers/plans/swebench_workspace/2026-05-20-owned-ecosystem-enrichment.md` | Current workspace owned-ecosystem enrichment plan. |

## Baseline Or Historical References

| File | Role |
|---|---|
| `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-topology-design.md` | Topology schema reference: `coordination_mode`, `agent_graph`, and validation rules. |
| `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-task-contract-design.md` | Task-contract schema reference: `evaluation_criteria`, `reward_basis`, predicate registry, and Stage 4 dispatch. |
| `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md` | Baseline six-family 680-row scaffold reference. Use for historical allocation math, not finalized domain behavior. |
| `docs/superpowers/specs/2026-05-14-swebench-workspace-asr-llm-judge-design.md` | Historical workspace ASR judge draft. Current reporting lives in `docs/superpowers/specs/swebench_workspace/llm_attack_success_evaluator.md`. |
| `docs/superpowers/specs/2026-05-14-swebench-workspace-stress-attack-redesign.md` | Historical workspace stress-attack draft. Current behavior lives in `docs/superpowers/specs/swebench_workspace/attack_vector_design.md`. |
| `docs/archive/superseded/` | Superseded design and plan files retained for audit history. |

## Branch Notes

`main` is the current working branch. `v2-refactor` and `phase-I-governance` remain checked out as historical/reference worktrees under `worktree/`; do not delete them without a separate cleanup review.
