# Phase 3 — Summary

Annotated summary of `phase-3-codex-raw.md`. Phase 3 delivered the 3-condition ablation, PolicyHook wiring, online AttributionGraph, and tool dispatch through 4 tasks (commits `686a1c0` → `74fa576`). 97/97 tests green.

## Codex's verdict

> *"Phase 3 meaningfully improves the message path, but the runtime still lacks true pre-tool enforcement, true online attribution, and a spec-faithful baseline. I would pitch this as an audit-aware prototype, not yet a complete audit-first runtime."*

## Six remaining architectural findings

1. **Baseline contamination** (spec §5.1 violation). The runner constructs `ActionLog`, `ShadowLog`, and `PhaseTracker` regardless of condition; the bus appends hash-chained records in baseline. Spec wants baseline to model a deployment WITHOUT audit infrastructure. Impact: benchmark ablation under-estimates the cost of enabling audit.
2. **Tool dispatch bypasses the audit boundary.** `TOOL_CALL` and `TOOL_OBSERVATION_RETURN` written directly via `action_log.append` — skip condition gating, PolicyHook, ShadowLog, PhaseTracker. Pre-tool enforcement cannot fire.
3. **Tool call/return linkage broken.** `TOOL_CALL` lacks model tool-call id; `TOOL_OBSERVATION_RETURN` lacks logged `TOOL_CALL.action_id`. Cannot pair request and response from log.
4. **Offline proximity-based attribution.** AttributionGraph built in EvalRunner post-run; L1 edges by "outbound_message within N later records" — conflates proximity with causal attribution. For Phase 4 with GT planted disclosures, must switch to explicit provenance links.
5. **Multi-hook enforce non-compositional.** Each hook sees original provisional, not post-rewrite. Order-sensitive. Blocked messages lose the rewritten/original evidence.
6. **Chain-fork race in `ActionLog`** (Phase 1 #4 still open). Tool dispatch makes this worse since tools write directly.

Plus Phase 1 carry-overs #5 (deep-mutable payload) and #6 (narrow protocols).

## Phase 3.5 remediation plan (~6 tasks, ~6–8 hours)

- **3.5a** Introduce `RawMessageBus` for true no-audit baseline; runner switches implementation on condition.
- **3.5b** Route tool dispatch through `AuditedMessageBus.record_tool_call(...)` / `record_tool_observation(...)` so hooks fire.
- **3.5c** `TOOL_CALL.action_id` flows into `TOOL_OBSERVATION_RETURN.payload["tool_call_action_id"]`.
- **3.5d** `AttributionGraph` becomes a runtime observer; edges derive from explicit provenance, not positional proximity.
- **3.5e** Multi-hook compositional: each hook sees current (post-previous-rewrites) content; `policy_decision` payload captures `target_action_id` + blocked/rewritten content.
- **3.5f** Chain-fork race fix: `BEGIN IMMEDIATE` transaction + `UNIQUE(agent_id, prev_hash)`.

All six should land before Phase 4 (scenario generator) — Phase 4 builds planted-disclosure metadata against the attribution layer, so that layer must be causal first.
