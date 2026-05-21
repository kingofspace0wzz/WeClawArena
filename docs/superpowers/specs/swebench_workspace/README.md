# SWE-bench Workspace Specs

Status: current as of 2026-05-20.

Code and data version checked: local working tree after the owned-ecosystem enrichment refresh. Do not treat this as a committed revision until the branch is committed.

This folder is the compact spec set for the `swebench_workspace` task family. It collects the current design after the v2.0.0 data build, resource-gated workflow changes, runtime attack overlays, and LLM-ASR judge work.

## Spec Map

- [data_construction.md](data_construction.md): how SWE-bench Lite rows become multi-user owned workspace scenarios.
- [task_success_metrics.md](task_success_metrics.md): utility metrics, pass criteria, and current no-attacker results.
- [attack_vector_design.md](attack_vector_design.md): resource-bound security, privacy, governance, and collaboration attacks.
- [llm_attack_success_evaluator.md](llm_attack_success_evaluator.md): LLM-as-a-judge schema and reporting rules for attack success.
- [owned_ecosystem_enrichment_design.md](owned_ecosystem_enrichment_design.md): resource-fact contract used to make owner files and DBs task-critical.

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

Local smoke checks run on 2026-05-20 after the owned-ecosystem enrichment refresh:

| Check | Result |
|---|---|
| published resource audit | 50 bases, 200 owners, 0 role-marker private notes, 200 non-empty `resource_facts` tables |
| focused workspace suite | 84 passed |
| calibration materializer | 50 bases, 250 variants |
| CI owner tool scope | `query_owned_table` allowed, `repo.write` still denied |

The active Python for verification was `.venv/bin/python` (Python 3.11). The global conda Python 3.13 environment segfaulted inside pytest capture before collection.

## Current Calibration Snapshot

The latest fully scored cap-normalized 50-base sweep used a common runtime `max_turns = 90` for all no-attacker rows and all matched attack rows before the owned-ecosystem enrichment refresh. Outputs are under `benchmark/phase5/pilot/swebench_workspace_cap90_50base_5mode_20260518_parallel_quiet`.

| Metric | Value |
|---|---:|
| rows run | 250 |
| no-attacker task success | 28/50 = 56.00% |
| attacked task success, scored rows | 121/194 = 62.37% |
| LLM-ASR, attack rows | 95/200 = 47.50% |
| no-attacker judge false positives | 0/50 = 0.00% |
| turn-cap rows | 94 |

For family-facing reporting, `swebench_workspace` should use task success as the main utility metric and LLM-ASR as the attack-success metric. Deterministic ASR should not be reported as a main metric for this family.

Post-enrichment no-attacker note: `benchmark/phase5/pilot/swebench_workspace_enriched_no_attacker_20260520_030432` ran all 50 no-attacker rows with `gpt-4.1-mini` and `max_turns = 90`. It produced 18 successes, 25 scored failures, and 7 unscored execution failures. The runner report gives 18/43 = 41.86% on scored rows; strict all-row TSR is 18/50 = 36.00%. Three unscored failures exposed a CI-owner tool-scope issue, now fixed and regenerated in the published bundles. A clean 50-row no-attacker rerun is needed before replacing the older calibration snapshot.
