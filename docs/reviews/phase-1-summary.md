# Phase 1 — Summary

Annotated summary of `phase-1-codex-raw.md`. Phase 1 delivered the core runtime skeleton through 13 TDD tasks (commits `2a065af` → `837ab3b`). 32/32 tests green; MVP demo end-to-end.

## Codex's critical findings (all resolved in Phase 1.5)

1. **Hash chain protects only `payload`, not envelope metadata.** Tampering with `social_phase`, `integrity_level`, `execution_phase`, `timestamp` silently passes `verify_chain`. SAF dimensions σ (Evidence Integrity) and φ (Phase-Scoped Policy Auditability) can be silently wrong while the chain reports intact.
2. **Opening message bypasses the audit substrate.** `ScenarioRunner.run` injected the opener via `bus._inner.send(...)` — violates the "MessageBus is sole egress" invariant.
3. **`AuditedMessageBus` manufactures phase metadata.** Every outbound hardcoded `NOMINAL`/`DISCOVERY`; dimension φ reduces to a trivial identity.

Reviewer-2 framing: *"The runtime does not yet justify an 'audit-first' claim, because the log is incomplete, non-causal, and integrity-protected only for payload text while the paper's scores depend on unprotected metadata."*

## Phase 1.5 remediation (4 commits)

- `474db69` hash full record envelope → fixes #1
- `5406592` log opening message as first-class audited action → fixes #2
- `d36ec75` wire PhaseTracker into AuditedMessageBus → fixes #3
- `b499b85` strengthen Phase 1 tests with verify_chain + more tamper coverage

All 3 critical resolved per `phase-1.5-codex-raw.md`.

## High-priority findings still open after Phase 1.5

- **#4 Chain-fork race** in `ActionLog` (separate connections for head-read and append; no BEGIN IMMEDIATE, no UNIQUE constraint). Still open after Phase 3.
- **#5 `ActionRecord` not deep-immutable** (payload is mutable dict). Still open.
- **#6 Protocol layer too narrow** (`MessageBus.send(content: str)` lacks envelope). Still open.

These roll into Phase 3.5 remediation (`HANDOFF-PHASE-4-ONWARDS.md`).

## Medium

- **#7 Tests pass happy path, not hard invariants** — partially resolved in Phase 1.5d. `test_protocols.py` remains tautological.
- **#8 Integrity semantics re: `signature`** — spec vs. impl mismatch; deferred for spec edit.
