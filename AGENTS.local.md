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
| Benchmark construction, scenario grid, task difficulty, world packs, and batch gates | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-benchmark-design.md` |
| Experimental protocol, run validation, metrics, batch reports, and compute planning | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-experimental-design.md` |
| Attack modes, concrete attack recipes, stress calibration, and attack-stage metrics | `docs/superpowers/specs/2026-05-08-clawsocialarena-v2-attack-vector-design.md` |
| Topology layer, coordination modes, agent_graph schema, and scenario validation | `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-topology-design.md` |
| Task contract shape, evaluation_criteria, reward_basis, predicate registry, and eval pipeline refactor | `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-task-contract-design.md` |
| Six task families, family-to-category allocation, per-family fixtures, and per-family attack payloads | `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md` |
| Benchmark data layout and teammate-facing run inspection guide | `docs/benchmark_dataset_guide.md` |

The generated `CLAUDE.md` and `agents/codex.md` files are agent-specific baseline references. Do not edit them directly; project-local overrides belong in this file or in per-agent local override files if those are created later.
