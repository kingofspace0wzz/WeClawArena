# SWE-bench Workspace Specs

Status: current as of 2026-05-18.

Code and data version checked: `main` at `d57ecc704f755718a3020094eec87615789a6edf`.

This folder is the compact spec set for the `swebench_workspace` task family. It collects the current design after the v2.0.0 data build, resource-gated workflow changes, runtime attack overlays, and LLM-ASR judge work.

## Spec Map

- [data_construction.md](data_construction.md): how SWE-bench Lite rows become multi-user owned workspace scenarios.
- [task_success_metrics.md](task_success_metrics.md): utility metrics, pass criteria, and current no-attacker results.
- [attack_vector_design.md](attack_vector_design.md): resource-bound security, privacy, governance, and collaboration attacks.
- [llm_attack_success_evaluator.md](llm_attack_success_evaluator.md): LLM-as-a-judge schema and reporting rules for attack success.

Historical design notes remain in `docs/superpowers/specs/2026-05-14-swebench-workspace-*.md`, `docs/superpowers/specs/2026-05-15-swebench-workspace-*.md`, and `docs/superpowers/specs/2026-05-16-swebench-workspace-*.md`. Scenario review reports remain in `docs/phase_5/scenarios/swebench_workspace/`.

## Current Published Data

Published path: `benchmark/scenarios/v2.0.0/swebench_workspace`.

The v2.0.0 manifest has:

| Item | Count |
|---|---:|
| base scenarios | 50 |
| `swebench_workspace` manifest rows | 250 |
| no-attacker rows | 50 |
| attack rows | 200 |
| attack modes per base | 4 |

Attack variants are not stored as fully copied `attack_variants/<mode>/` folders. The published store carries base bundles, and the runner materializes attack variants at runtime through `clawsocialarena.attacks.runtime_overlay.materialize_runtime_variant`.

## Latest Smoke Checks

Local smoke checks run on 2026-05-18:

| Check | Result |
|---|---|
| manifest and base bundle integrity | 250 rows, 50 bases, 50 no-attacker rows, 0 missing base files |
| runtime attack overlay | security variant materialized, metadata written, one injected message |
| focused test suite | 51 passed, 1 skipped |

The skipped test is expected on machines without the optional local SWE-bench environment resource mirror under `knowledge/SWE-bench/swebench/resources/swebench-og`.

## Current Calibration Snapshot

The current cap-normalized 50-base sweep used a common runtime `max_turns = 90` for all no-attacker rows and all matched attack rows. Outputs are under `benchmark/phase5/pilot/swebench_workspace_cap90_50base_5mode_20260518_parallel_quiet`.

| Metric | Value |
|---|---:|
| rows run | 250 |
| no-attacker task success | 28/50 = 56.00% |
| attacked task success, scored rows | 121/194 = 62.37% |
| LLM-ASR, attack rows | 95/200 = 47.50% |
| no-attacker judge false positives | 0/50 = 0.00% |
| turn-cap rows | 94 |

For family-facing reporting, `swebench_workspace` should use task success as the main utility metric and LLM-ASR as the attack-success metric. Deterministic ASR should not be reported as a main metric for this family.
