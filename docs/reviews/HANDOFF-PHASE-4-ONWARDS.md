# Handoff — Phase 4 onwards

**State at handoff (2026-04-15):** Phase 1 + 1.5 + 2 + 2.5 + 3 merged to master. 97/97 tests green. MVP demo works end-to-end.

## What is DONE

- **Core runtime skeleton**: `ActionRecord`, `ActionLog` SQLite w/ full-envelope hash chain, 4 Protocol interfaces, `InProcessMessageBus`, `AuditedMessageBus`, `AuditableAIAgent`, `ScenarioRunner`, scheduling task, MVP fixture.
- **Phase 1.5 remediations**: full-envelope hashing, opening-message logging, PhaseTracker wiring, strengthened tests.
- **SAF framework**: 5 scorers (Recoverability, Policy Checkability, Attribution, Evidence Integrity, Phase-Scoped Policy) + SAFScorer geometric-mean orchestrator.
- **ShadowLog**, `PolicyRegistry` w/ flat + phase-scoped predicates, `PolicyCatalog` (kind → predicate).
- **Vendored**: SEM stub, error_chains classifier (trimmed), graph/topology (stubbed).
- **`EvalRunner` 5-stage pipeline** + `RunScorecard` JSON.
- **Phase 3**: PolicyHook wiring (baseline/passive/enforce) + rule-based DLP hook + online AttributionGraph (proximity-based) + tool dispatch in `AuditableAIAgent`.

Package lives at `/home/kingofspace0wzz/llm/mas/clawsocialarena/`. Spec at `docs/superpowers/specs/2026-04-15-clawsocialarena-design.md`. Plan at `docs/superpowers/plans/2026-04-15-clawsocialarena-plan.md` (note: `plans/` is gitignored).

## What is OPEN (Phase 3.5 architectural debt)

Captured in `phase-3-summary.md`. Must be fixed before Phase 4 starts:

1. **Baseline contamination** — baseline still pays audit logging cost; need `RawMessageBus` for true no-audit baseline.
2. **Tool dispatch bypasses audit boundary** — TOOL_CALL writes direct to log, skips hooks/shadow/phase-tracker.
3. **Tool call/return linkage broken** — TOOL_OBSERVATION_RETURN doesn't reference TOOL_CALL.action_id.
4. **Offline proximity-based attribution** — should be online + causal via explicit provenance links.
5. **Multi-hook enforce non-compositional** — each hook sees original provisional, not post-rewrite.
6. **Chain-fork race** (Phase 1 high #4) — matters once concurrent writers arrive.

Plus Phase 1 carry-overs:
- ActionRecord payload deep-mutable (Phase 1 #5)
- MessageBus.send(content: str) narrow; needs MessageEnvelope (Phase 1 #6)

## Phase 3.5 remediation tasks

- **3.5a** Introduce `RawMessageBus` for true no-audit baseline. Runner switches impl on condition. ~1 hour.
- **3.5b** Route tool dispatch through `AuditedMessageBus.record_tool_call(...)` / `record_tool_observation(...)`. Tool hooks become a first-class hook class. ~1.5 hours.
- **3.5c** `TOOL_CALL.action_id` flows into `TOOL_OBSERVATION_RETURN.payload["tool_call_action_id"]`. ~30 min.
- **3.5d** Online attribution: `AttributionGraph` is a runtime observer; edges are explicit provenance links (source_action_id, target_action_id). ~2 hours.
- **3.5e** Multi-hook compositional: each hook sees CURRENT provisional; `policy_decision` payload captures `target_action_id` and the blocked/rewritten content. ~1 hour.
- **3.5f** Chain-fork race fix: `BEGIN IMMEDIATE` transaction in `ActionLog.append` + `UNIQUE(agent_id, prev_hash)`. ~1 hour.

Total ~6–8 hours.

## Phases 4–6 high-level

Per plan at `docs/superpowers/plans/2026-04-15-clawsocialarena-plan.md`.

### Phase 4 — Scenario generator with mechanical GT (~7 sub-tasks)

- 4.1 Template protocol + CU × Scheduling template + tests
- 4.2 Instantiation layer (LLM-assisted; reads AgentSocialBench profiles from `/home/kingofspace0wzz/llm/mas/agent-socialn-privacy/prism/data/profiles/`)
- 4.3 Attack injection layer (6 attacker types)
- 4.4 GT assembly layer (emits scenario.gt.json with planted disclosures, phase schedule, attribution DAG)
- 4.5 Remaining 13 category × task-family templates
- 4.6 CLI `python -m clawsocialarena.generator.cli --category CU --family scheduling --n 10 --seed 42`
- 4.7 Generate 10 sample scenarios per (category, family) pair

**Requires**: at least one LLM API key (Bedrock + Anthropic recommended).

### Phase 5 — Full 250-scenario benchmark + external baselines

- 5.1 Generate 250 scenarios + manifest + 3 disagreement vignettes + 40-scenario validation sample
- 5.2 Three external comparison baselines (prompt-only L0-L4, DLP sanitizer, vanilla-AA post-hoc auditor)
- 5.3 Pre-registration file committed

### Phase 6 — Experiments + analysis + paper artifacts

- ~5,400 runs across 4 models × 3 conditions × 250 scenarios + ablations
- Aggregator + headline tables + ablation figures + sensitivity analysis + reproducibility bundle
- Pre-registration reconciliation

**Requires**: ~$3–8K cloud compute budget, 7–10 days wall-clock, API access to all 4 model providers.

## Recommended resume plan

1. **Phase 3.5 first** (before Phase 4). Required for benchmark numbers to be trustable.
2. **Phase 4 next**, needs at least one LLM API key. Can be done locally with Bedrock once credentials are configured.
3. **Phase 5** builds on Phase 4 output.
4. **Phase 6** is the experimental run — needs budget + time.

Each phase ends with Codex review per the per-phase protocol.

## Worktree convention (updated preference)

Per 2026-04-15 user preference, use:

```bash
git worktree add -b feat/<name> /home/kingofspace0wzz/llm/mas/worktree/<name> master
```

NOT a sibling path like `../mas-<name>`. The `.gitignore` excludes `worktree/` so contents don't pollute `git status`.

## Tests

From `/home/kingofspace0wzz/llm/mas/clawsocialarena/`:

```bash
uv venv --python 3.11
uv pip install -e ".[dev]"
.venv/bin/pytest -v       # expect 97/97
.venv/bin/python -m scripts.run_mvp   # expect terminal_predicate_passed=True
```

## Artifact inventory

- Spec: `docs/superpowers/specs/2026-04-15-clawsocialarena-design.md` (tracked)
- Plan: `docs/superpowers/plans/2026-04-15-clawsocialarena-plan.md` (gitignored — on disk only)
- Reviews: `docs/superpowers/reviews/` (this directory)
