# Project-Local Agent Instructions

## Next-Step Reporting

At the end of every conversation turn, explicitly state the recommended next step. The next step should be concrete and scoped to the current project state, for example a phase to execute, a verification to run, a design decision to make, or a blocker that needs user input.

When doing implementation work, think through the next step before responding and include it in the final response even if the current task is incomplete. If there are multiple plausible next steps, recommend one and explain the tradeoff briefly.

## Project Documentation References

Before making benchmark, runtime, evaluation, or documentation changes, use these current project references:

| Need | Read |
|---|---|
| Current branch, retained batch, and benchmark target status | `docs/project_status.md` |
| Documentation map | `docs/DOCUMENTATION_INDEX.md` |
| Runtime, policy hooks, Multi-Party Social World Model, and Social Auditability Framework design | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-runtime-saf-design.md` |
| Benchmark construction, scenario grid, task difficulty, bundle-local scenario worlds, and batch gates | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-benchmark-design.md` |
| Experimental protocol, run validation, metrics, batch reports, and compute planning | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-experimental-design.md` |
| Attack modes, concrete attack recipes, stress calibration, and attack-stage metrics | `docs/superpowers/specs/2026-05-08-clawsocialarena-v2-attack-vector-design.md` |
| Current MARBLE bargaining task construction, attack vectors, evaluation metrics, and design history | `docs/superpowers/specs/bargaining/README.md` |
| Bargaining implementation-plan history and next-plan pointer | `docs/superpowers/plans/bargaining/README.md` |
| Topology layer, coordination modes, agent_graph schema, and scenario validation | `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-topology-design.md` |
| Task contract shape, evaluation_criteria, reward_basis, predicate registry, and eval pipeline refactor | `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-task-contract-design.md` |
| Six task families, family-to-category allocation, per-family fixtures, and per-family attack payloads | `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md` |
| Benchmark data layout and teammate-facing run inspection guide | `docs/benchmark_dataset_guide.md` |

For MARBLE bargaining work, start with `docs/superpowers/specs/bargaining/README.md`, then read the three active 2026-05-16 specs for task construction, attack vectors, and evaluation metrics. The shallow price-only bargaining rows and delegated-close calibration docs are archived history and should not guide new benchmark construction unless a new plan explicitly references them.

The generated `CLAUDE.md` and `agents/codex.md` files are agent-specific baseline references. Do not edit them directly; project-local overrides belong in this file or in per-agent local override files if those are created later.

## Benchmark Calibration Goal

The calibration target should not be "make all no-attacker rows pass." It should be a non-perfect but scoreable baseline. Treat no-attacker task failures as useful benchmark signal when the row still materializes, runs through the substrate, writes scorecard evidence, and can distinguish ordinary task failure from attack-caused harm.

## Local Environment

Before running paid benchmark simulations, pilot batches, LLM judge passes, or any command that requires provider credentials, load the repo-local `.env` file when it exists. The OpenAI API key for this project is stored there. Source it without printing secrets, for example:

```bash
set -a
source .env
set +a
```
