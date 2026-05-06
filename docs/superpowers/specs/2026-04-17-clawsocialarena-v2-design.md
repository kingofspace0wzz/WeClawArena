# ClawSocialArena v2 Design Specification

**Status:** Superseded as the canonical monolithic design reference on 2026-05-06.

The April 17 monolith has been split into three current design specs:

| Need | Current spec |
|---|---|
| Harms-first motivation, threat model, runtime architecture, policy hooks, MSWM, and SAF | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-runtime-saf-design.md` |
| Benchmark construction, scenario grid, attack modes, world packs, task difficulty, and batch gates | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-benchmark-design.md` |
| Experimental protocol, run validation, metrics, batch-report requirements, aggregation, and compute planning | `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-experimental-design.md` |

For current branch, retained batch, and benchmark-target status, read `docs/project_status.md`. For the full documentation map, read `docs/DOCUMENTATION_INDEX.md`.

Agent context references:

| File | Role |
|---|---|
| `AGENTS.md` | Shared cross-agent baseline instructions. |
| `AGENTS.local.md` | Project-local cross-agent overrides and current project doc entry points. |
| `CLAUDE.md` | Generated Claude-specific baseline instructions. Do not edit directly. |
| `agents/codex.md` | Generated Codex-specific baseline instructions. Do not edit directly. |
