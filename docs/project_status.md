# ClawSocialArena Current Project Status

**Last updated:** 2026-05-20

This is the compact entry point for current project state. Older specs and plans remain in git history or archive folders, but they are not execution instructions unless this file or a current domain spec points to them.

## Branch And Worktrees

The active checkout is `main` at `/Users/princewang/llm/mas/clawsocialarena`.

Two legacy worktrees are still present:

| Worktree | Branch | Current role |
|---|---|---|
| `worktree/v2-refactor` | `v2-refactor` | Historical/reference branch. Do not delete until its unique scenario docs and template changes are compared against the current generator. |
| `worktree/phase-I-governance` | `phase-I-governance` | Historical/reference branch. Do not delete until governance and profile-loader content is confirmed present in `main`. |

## Current Benchmark Stores

| Layer | Path | Role |
|---|---|---|
| Published v2.0.0 scenario store | `benchmark/scenarios/v2.0.0` | Active base-bundle store and manifest for finalized domain sweeps, runtime overlays, and LLM-ASR judging. |
| Baseline Phase 5 scaffold | `benchmark/phase5/scaffold` | Historical 680-row scaffold and 14-cell matched-grid reference. Useful for allocation math, not the only current target. |

The current published manifest is `benchmark/scenarios/v2.0.0/manifest.json`.

| Family | Bases | Manifest rows | Current role |
|---|---:|---:|---|
| `marble_bargaining` | 24 | 120 | Finalized owned-ecosystem bargaining slice, cap-36, LLM-ASR reporting. |
| `marble_bidding` | 12 | 60 | Finalized owned-ecosystem bidding slice, seller-centered close, LLM-ASR reporting. |
| `travel` | 20 | 100 | Finalized TravelBench-derived CU-D and MG-C slice, cap-36, travel LLM-ASR judge. |
| `swebench_workspace` | 50 | 250 | Finalized SWE-bench Lite owned-workspace slice, cap-90 calibration override, workspace LLM-ASR judge. |
| `tau2_retail` | 24 | 120 | Published retail family-pack slice. |
| `marble_research` | 8 | 40 | Published research family-pack slice. |
| **Total** | **138** | **690** | Active v2.0.0 manifest. |

Every base has five matched modes: `no_attacker`, `collaboration`, `security`, `privacy`, and `governance`.

## Current Canonical Docs

| Need | Current file |
|---|---|
| Documentation map | `docs/DOCUMENTATION_INDEX.md` |
| Benchmark data inspection | `docs/benchmark_dataset_guide.md` |
| Runtime and SAF | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-runtime-saf-design.md` |
| Benchmark construction | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-benchmark-design.md` |
| Evaluation and reporting | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-experimental-design.md` |
| Attack layer | `docs/superpowers/specs/2026-05-08-clawsocialarena-v2-attack-vector-design.md` |
| Bargaining domain | `docs/superpowers/specs/bargaining/README.md` |
| Bidding domain | `docs/superpowers/specs/bidding/README.md` |
| Travel domain | `docs/superpowers/specs/travel/README.md` |
| SWE-bench workspace domain | `docs/superpowers/specs/swebench_workspace/README.md` |

## Current Rules

- `driver_orchestrated_docker` is the benchmark-valid runtime. `host_session` is development-only.
- Attack rows in the published store are materialized at run time through `clawsocialarena.attacks.runtime_overlay.materialize_runtime_variant`.
- Do not describe published finalized domains as pending LLM-naturalization targets. Travel and workspace use reviewed source-derived seed materialization with `naturalization_model = none`; bargaining and bidding use owned-ecosystem seed generators.
- Domain reports must keep utility separate from attack success. Use TSR or task success for utility. Use domain LLM-ASR for attack success in bargaining, bidding, travel, and `swebench_workspace`.
- Deterministic attack-success columns are diagnostics for finalized domains unless the domain spec says otherwise.
- Older scaffolds and pre-Phase-5 category sweeps are historical references. Do not use them as current benchmark claims.

## Next Step

Finish domain-level report alignment for `benchmark/scenarios/v2.0.0`: fold the latest judged outputs into family reports, verify that each finalized domain reports utility separately from LLM-ASR, and only then decide whether to expand the older scaffold or create a broader release package.
