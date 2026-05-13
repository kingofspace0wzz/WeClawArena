# ClawSocialArena Current Project Status

**Last updated:** 2026-05-13

This is the current entry point for project state. Older design specs and plans remain useful as historical records, but they should not be used as execution instructions unless this file points to them. Specs earlier than 2026-05-06 are historical and are no longer active Phase 5 design references.

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
| Runtime and SAF design | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-runtime-saf-design.md` |
| Benchmark construction design | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-benchmark-design.md` |
| Experimental design | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-experimental-design.md` |
| Attack vector and stress-attack design | `docs/superpowers/specs/2026-05-08-clawsocialarena-v2-attack-vector-design.md` |
| Family pack design | `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md` |
| Topology design | `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-topology-design.md` |
| Task contract design | `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-task-contract-design.md` |
| Benchmark dataset guide | `docs/benchmark_dataset_guide.md` |

The April 17 implementation plan has been archived because it had become a long historical execution log. Its old path now contains a pointer stub.

## Current Benchmark Target

The current benchmark design is the Phase 5 family-pack scaffold under `benchmark/phase5/scaffold`. The scaffold is structurally complete for the 680-row balanced pilot, but the paid scenario-naturalization and full simulation pass are not complete. The release-ready dataset should not be claimed until the naturalized bundles, trajectories, scorecards, and QC reports are materialized under `benchmark/phase5/v2.0.0`.

The active Phase 5 scaffold target is:

| Stratum | Count |
|---|---:|
| Main matched variants | 630 |
| Hard-verification variants | 25 |
| Episode-graph variants | 20 |
| Audit challenge cases | 5 |
| **Total** | **680** |

The 630 main matched variants come from 126 base tasks. The base tasks are distributed as 14 category/family cells × 3 task variants × 3 scaffold-tier slots. The `tier1`, `tier2`, and `tier3` path names are legacy scaffold identifiers kept for index stability; they should not be described as validated task-complexity tiers. Each base task has five attack-mode variants: `no_attacker`, `collaboration`, `security`, `privacy`, and `governance`.

The earlier 550-variant tree and the pre-Phase 5 category-sweep batches are historical diagnostics, not the current benchmark target. The later release grid may expand to 1100 variants if the 680-variant pilot validates task quality, trajectory quality, attack pressure, and audit evidence coverage.

| Stage | Main base tasks | Main variants | Total variants | Current role |
|---|---:|---:|---:|---|
| Phase 5 balanced pilot | 126 | 630 | 680 | Active scaffold and naturalization target. |
| Conditional release grid | 210 | 1050 | 1100 | Scale-out target only after pilot review. |

## Phase 5 Dataset State

`benchmark/phase5/scaffold` is the canonical generated scaffold. It contains:

| File or directory | Role |
|---|---|
| `phase5_base_index.json` | Index of the 126 base scenario bundles. |
| `phase5_variants_index.json` | Index of the 630 main matched attack-mode variants. |
| `phase5_manifest.json` | Combined 680-row manifest, including 630 main variants and 50 supplementary rows. |
| `<cell_id>/task<k>/tier<t>/` | Bundle-local scenario world for one base task and scaffold-tier slot. |
| `<cell_id>/task<k>/tier<t>/attack_variants/<attack_mode>/` | Attack-mode overlay for one adversarial variant. |

The scaffold has 14 cells:

| Category | Family A | Family B | Base tasks | Main variants |
|---|---|---|---:|---:|
| Cross-Domain | `marble_research` | `tau2_airline` | 18 | 90 |
| Mediated Communication | `wildclaw_social` | `tau2_airline` | 18 | 90 |
| Cross-User agent-to-agent | `marble_bargaining` | `tau2_retail` | 18 | 90 |
| Multi-Party Group | `tau2_telecom` | `marble_research` | 18 | 90 |
| Hub-and-Spoke | `marble_research` | `tau2_telecom` | 18 | 90 |
| Competitive | `marble_bargaining` | `wildclaw_social` | 18 | 90 |
| Affinity-Modulated | `tau2_retail` | `tau2_telecom` | 18 | 90 |

Each scaffold bundle contains `scenario.json`, `scenario.gt.json`, `phase5_metadata.json`, `family_pack_context.json`, persona files, tool manifests, governance manifests, and attack-variant overlays. These are deterministic scaffold artifacts. They are not yet the final naturalized dataset.

The expected release layout is `benchmark/phase5/v2.0.0`. That directory should be created only after scenario naturalization has produced accepted naturalized bundles. It should contain a release manifest, indexes copied or derived from the scaffold, naturalized scenario bundles, run artifacts for accepted simulations, scorecards, and QC reports. See `docs/benchmark_dataset_guide.md` for the expected layout.

## Historical Batch Status

Older retained batch directories are diagnostic only. This includes `batch-0061-resource-label-sanitized-25`, `batch-0064-construction-metrics-fixes-50`, `batch-0065-scale-gate-50-idx075`, `batch-0067-category-sweep-000-postcommit`, `batch-0068-category-sweep-001`, `batch-0069-category-sweep-002`, `batch-0071-condition-sentinel-0069`, `batch-0072-category-sweep-003-merged-rerun1`, and `batch-0073-category-sweep-004`.

These runs remain useful for regression diagnosis, but they predate the Phase 5 family-pack scaffold and should not be used as release benchmark evidence.

## Next Step

The next execution step is to finish Phase 5 scenario naturalization and publish the accepted naturalized bundles under `benchmark/phase5/v2.0.0`. After that release directory exists, run the smoke-before-batch protocol on representative rows, then simulate and score the 680-row pilot with QC reports before any 1100-row release-grid expansion.
