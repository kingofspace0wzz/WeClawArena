# Project-Local Agent Instructions

## Next-Step Reporting

At the end of every conversation turn, state the recommended next step. Keep it concrete and scoped to the current project state: a verification to run, a domain report to update, a design choice to make, or a blocker that needs user input.

## Current Specs To Read First

Before benchmark, runtime, evaluation, attack, or documentation work, use this compact reading order:

| Need | Read |
|---|---|
| Current branch, store, and benchmark status | `docs/project_status.md` |
| Documentation map | `docs/DOCUMENTATION_INDEX.md` |
| Runtime, policy hooks, MSWM, and SAF | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-runtime-saf-design.md` |
| Current benchmark construction | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-benchmark-design.md` |
| Current evaluation and reporting | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-experimental-design.md` |
| Current attack layer | `docs/superpowers/specs/2026-05-08-clawsocialarena-v2-attack-vector-design.md` |
| Benchmark data inspection | `docs/benchmark_dataset_guide.md` |

## Current Domain Specs

The finalized active domains are:

| Domain | Spec entry point | Store | Rows | Utility metric | Attack metric |
|---|---|---|---:|---|---|
| `marble_bargaining` | `docs/superpowers/specs/bargaining/README.md` | `benchmark/scenarios/v2.0.0/bargaining/` | 120 | raw TSR | LLM-ASR |
| `marble_bidding` | `docs/superpowers/specs/bidding/README.md` | `benchmark/scenarios/v2.0.0/bidding/` | 60 | raw TSR | LLM-ASR |
| `travel` | `docs/superpowers/specs/travel/README.md` | `benchmark/scenarios/v2.0.0/travel/` | 100 | travel task success | travel LLM-ASR |
| `swebench_workspace` | `docs/superpowers/specs/swebench_workspace/README.md` | `benchmark/scenarios/v2.0.0/swebench_workspace/` | 250 | workspace task success | workspace LLM-ASR |

`tau2_retail` and `marble_research` are also present in the published v2.0.0 manifest, but the four domains above are the current finalized benchmark-design focus. Older shallow bargaining, lightweight bidding, pre-redesign travel, and pre-enrichment workspace material are historical only unless a current plan cites them.

## Reporting Rules

Keep utility and attack success separate. Do not fold task failure into ASR.

- Utility: report TSR or task success, plus turn caps, runtime errors, and stage coverage.
- Attack success: report the domain LLM-ASR judge for bargaining, bidding, travel, and `swebench_workspace`.
- Deterministic attack columns are diagnostics unless the domain spec says otherwise.
- No-attacker failures are useful benchmark signal when the row is scoreable. Do not calibrate by forcing every no-attacker row to pass.

## Runtime And Store Rules

Use `benchmark/scenarios/v2.0.0/manifest.json` as the current published-store manifest. Attack rows point to base bundles. Runtime variants are materialized on demand through `clawsocialarena.attacks.runtime_overlay.materialize_runtime_variant`; do not expect fully copied `attack_variants/<mode>/` folders in the published domain stores.

`driver_orchestrated_docker` is the benchmark-valid runtime substrate. `host_session` is development-only. `containerized_multi_agent` remains a future stronger substrate, not a current blocker.

Generated `CLAUDE.md` and `agents/codex.md` are baseline references. Do not edit them directly; project-local overrides belong here or in per-agent local override files.

## Local Environment

Before paid simulations, pilot batches, LLM judge passes, or any command requiring provider credentials, load the repo-local `.env` when it exists without printing secrets:

```bash
set -a
source .env
set +a
```
