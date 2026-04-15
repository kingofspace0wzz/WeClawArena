**Findings**

- Critical: the “integrity” chain does not protect the fields SAF will score on. [action_log.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/action_log.py:76) hashes only `payload`; [verify_chain()](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/action_log.py:106) recomputes from `payload` plus `prev_hash` only. I verified that direct SQL tampering of `social_phase` and `integrity_level` still leaves `verify_chain("alice") == True`. That means Phase 2 can silently score wrong `φ`, `σ`, and even `ψ` while the system reports an intact chain.

- Critical: the runtime already bypasses the audit substrate. [runner.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/runtime/runner.py:63) injects the opening message via `bus._inner.send(...)` specifically to avoid logging it. That violates the stated completeness invariant. Any Action Recoverability or shadow-log comparison in Phase 2 starts from a known hole unless you special-case “unlogged but real” actions everywhere.

- Critical: `AuditedMessageBus` is manufacturing metadata and dropping causality. [audited.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/bus/audited.py:35) hardcodes every outbound as `ExecutionPhase.NOMINAL` and `SocialPhase.DISCOVERY`; [message_bus.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/protocols/message_bus.py:8) only transports bare `content`; [in_process.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/bus/in_process.py:19) returns only `(sender_id, content)`. Phase-scoped policy auditability and attribution DAGs need real message envelopes, causal IDs, and actual phase context. Right now they cannot be recovered.

- High: there is a latent chain-fork race in `ActionLog`. [action_log.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/action_log.py:70) reads head on one connection, then inserts on another, with no transaction and no `UNIQUE(agent_id, prev_hash)` guard. In the current single-event-loop MVP it mostly hides, but the moment Phase 2 introduces concurrent scoring/logging helpers or any threaded transport, two writes can observe the same head and both append.

- High: `ActionRecord` is not actually immutable, and the schema is too weak for Phase 2. [types.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/types.py:51) sets `frozen=True`, but `payload` is a mutable `dict`; I verified `rec.payload["x"] = 2` succeeds after construction. Combined with raw `timestamp: str` and untyped payloads, this is a trap for shadow logs and typed scorers. The enum list is fine; the record schema is not.

- High: the protocol layer is too narrow and too stringly. `MessageBus` needs an envelope object, not `content: str`; `PolicyHook.evaluate(...)` in [policy_hook.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/protocols/policy_hook.py:23) is sync and contextless for what will likely become async, evidence-aware policy checks; `ScenarioIO` in [scenario_io.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/protocols/scenario_io.py:5) returns raw dicts, throwing away type safety exactly where GT fidelity matters.

- Medium: the tests are green but do not prove the hard invariants. [test_runner.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/tests/test_runtime/test_runner.py:11) never asserts `terminal_predicate_passed`, the pinned slot, or chain verification. [test_audited.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/tests/test_bus/test_audited.py:9) checks only “a row exists” and “inner got a message,” not causal identity, failure semantics, or phase metadata. [test_protocols.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/tests/test_protocols.py:4) is basically a tautology. The suite proves the happy path demo, not the auditability claims.

- Medium: integrity semantics are internally inconsistent. [types.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/types.py:70) only requires `signature` at `CROSS_AGENT_SIGNED`, while the spec says signature is present for integrity level `>= 3`. [audited.py](/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/clawsocialarena/bus/audited.py:45) emits `HASH_CHAINED` records with no signature. Until this is reconciled, SAF dimension `σ` is underspecified.

**Direct Answers**

- `ActionLog` + `AuditedMessageBus`: yes, there are correctness bugs that will contaminate Phase 2 scores now, not just later.
- Biggest Phase 2 debt: lack of typed message/action envelopes and causal links. That is the corner you are painting yourselves into.
- `ActionType` enum itself is sufficient for the 10 types. `ActionRecord` is not. It needs typed payloads plus explicit causal/phase/evidence fields before Phase 2.
- Protocols: `ActionLogger` is salvageable; `MessageBus` and probably `PolicyHook` need redesign before Phase 2, not after.
- TDD hygiene: acceptable for scaffolding, weak for systems claims.
- Missed from the 23 followups: payload-only hashing, fake phase metadata, deep-mutable `ActionRecord`, and the fact that the opening-message bypass is functionally blocking for recoverability, not “non-blocking.”
- Reviewer-2 objection: the runtime does not yet justify an “audit-first” claim, because the log is incomplete, non-causal, and integrity-protected only for payload text while the paper’s scores depend on unprotected metadata.

Verified locally: `/home/kingofspace0wzz/llm/mas-clawsocialarena/clawsocialarena/.venv/bin/pytest -q` reports `32 passed`.
