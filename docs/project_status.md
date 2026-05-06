# ClawSocialArena Current Project Status

**Last updated:** 2026-05-06

This is the current entry point for project state. Older design specs and plans remain useful as historical records, but they should not be used as execution instructions unless this file points to them.

## Current Branch And Worktrees

The active checkout is `main` at `/Users/princewang/llm/mas/clawsocialarena`.

Two legacy worktrees are still present:

| Worktree | Branch | Current role |
|---|---|---|
| `worktree/v2-refactor` | `v2-refactor` | Historical/reference branch. It diverges from `main` and should not be deleted until its unique scenario docs and template changes are compared against the current generator. |
| `worktree/phase-I-governance` | `phase-I-governance` | Historical/reference branch. It diverges from `main` and should not be deleted until governance and profile-loader content is confirmed present in `main`. |

Do not remove either worktree or branch without an explicit cleanup review. The current documentation cleanup only records their status.

## Canonical Documentation

| Purpose | Current file |
|---|---|
| Project status and branch map | `docs/project_status.md` |
| Documentation map | `docs/DOCUMENTATION_INDEX.md` |
| Team-facing system design | `docs/superpowers/specs/2026-04-24-clawsocialarena-v2-team-design.md` |
| Runtime and SAF design | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-runtime-saf-design.md` |
| Benchmark construction design | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-benchmark-design.md` |
| Experimental design | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-experimental-design.md` |
| Benchmark dataset guide | `docs/benchmark_dataset_guide.md` |
| Task difficulty design | `docs/superpowers/specs/2026-05-05-task-difficulty-success-calibration-design.md` |
| LLM naturalization and batch pipeline design | `docs/superpowers/specs/2026-05-02-llm-naturalization-batch-pipeline-design.md` |

The April 17 implementation plan has been archived because it had become a long historical execution log. Its old path now contains a pointer stub.

## Current Benchmark Target

The current scaffold target is the 680-variant balanced difficulty pilot:

| Stratum | Count |
|---|---:|
| Main matched variants | 630 |
| Hard-verification variants | 25 |
| Episode-graph variants | 20 |
| Audit challenge cases | 5 |
| **Total** | **680** |

The earlier 550-variant tree is a pre-calibration scaffold, not the final benchmark target. The later release grid may expand to 1100 variants if the 680-variant pilot validates the designed difficulty tiers.

| Stage | Main base tasks | Main variants | Total variants | Current role |
|---|---:|---:|---:|---|
| Balanced difficulty pilot | 126 | 630 | 680 | Active target for corrected gate runs. |
| Conditional release grid | 210 | 1050 | 1100 | Scale-out target only after pilot review. |

## Current Batch Status

The only retained batch directories are:

| Batch | Status |
|---|---|
| `batch-0061-resource-label-sanitized-25` | Diagnostic only. Old scorecard metrics are affected by evaluator fixes. |
| `batch-0064-construction-metrics-fixes-50` | Diagnostic only. Old scorecard metrics are affected by evaluator fixes. |
| `batch-0065-scale-gate-50-idx075` | Diagnostic only. Old metrics are affected by evaluator fixes and by the AM scheduling/naturalization construction fixes. |

These retained batches should not be used as final benchmark evidence. The next benchmark step is to rerun corrected replacement gates from indexes `0`, `25`, and `75`, review the generated tasks and trajectories, then continue scale-out only if the review passes.

The retained runs correspond to these replacement-gate slices of the current 680-variant scaffold:

| Retained batch / replacement gate | Index window | Variants | Base tasks | Category and family cells | Designed difficulty mix | Attack-mode mix |
|---|---:|---:|---:|---|---|---|
| `batch-0061-resource-label-sanitized-25` / rerun `start-index 0`, `batch-size 25` | 0-24 | 25 | 5 | Cross-User agent-to-agent Scheduling: 25 variants / 5 bases | easy: 15; realistic: 10 | 5 per mode |
| `batch-0064-construction-metrics-fixes-50` / rerun `start-index 25`, `batch-size 50` | 25-74 | 50 | 10 | Cross-User agent-to-agent Scheduling: 20 variants / 4 bases; Mediated Communication Scheduling: 30 variants / 6 bases | easy: 15; realistic: 20; stress: 15 | 10 per mode |
| `batch-0065-scale-gate-50-idx075` / rerun `start-index 75`, `batch-size 50` | 75-124 | 50 | 10 | Affinity-Modulated Scheduling: 35 variants / 7 bases; Mediated Communication Scheduling: 15 variants / 3 bases | easy: 15; realistic: 15; stress: 20 | 10 per mode |

## Recent Corrections That Affect Old Runs

The current code fixes several issues found during review:

| Area | Correction |
|---|---|
| AM scheduling construction | Three-participant AM scheduling now binds to three distinct users. |
| Naturalized protected content | Busy/free availability is not automatically scored as a privacy leak; sensitive reasons and private details remain protected. |
| Governance scoring | Governance seed actions are not counted as downstream governance attack success. |
| Security scoring | Harmful-content diffusion is counted from downstream propagation, not only from resource/tool attacks. |
| Privacy matching | Date/time protected-content patterns support common paraphrases such as month-name disclosures. |

Because these corrections change construction and evaluation semantics, old batch metrics should be treated as diagnostic only.

## Next Step

Rerun replacement gate batches with the corrected scaffold and evaluator:

```bash
scripts/naturalize_and_run_batch.py --start-index 0 --batch-size 25
scripts/naturalize_and_run_batch.py --start-index 25 --batch-size 50
scripts/naturalize_and_run_batch.py --start-index 75 --batch-size 50
```

Use the project-standard model settings from the batch runner: `gpt-5` for naturalization and `gpt-4.1-mini` for simulated agents. Stop after each gate for task-quality and trajectory review.
