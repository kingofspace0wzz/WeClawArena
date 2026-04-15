**Findings**

1. **CRITICAL 1 — RESOLVED.** `clawsocialarena/action_log.py:48-66` adds `_canonical_envelope()` covering `action_id`, `agent_id`, `action_type`, `timestamp`, `execution_phase`, `social_phase`, `payload`, `integrity_level`, `signature`. `append()` now hashes that envelope at `action_log.py:101-103`; `verify_chain()` re-derives the same fields at `action_log.py:139-150`. Regression coverage landed in `tests/test_action_log.py:83-145` for `social_phase`, `integrity_level`, `execution_phase`, `timestamp` tampering.

2. **CRITICAL 2 — RESOLVED.** The opener no longer bypasses the bus. `runtime/runner.py:72-75` now sends the opening message through `self.bus.send(...)` instead of `_inner.send(...)`. `tests/test_runtime/test_runner.py:40-49` asserts the opening message appears in the action log exactly once.

3. **CRITICAL 3 — RESOLVED.** `bus/audited.py:39-41` now reads `social_phase` from `PhaseTracker` when provided; `runtime/runner.py:46-56` constructs and injects a tracker, and `runner.py:77-79` advances it per turn. Coverage exists in `tests/test_bus/test_audited.py:31-44` and `tests/test_audit/test_phase_tracker.py:10-19`.

4. **HIGH 4 — NOT RESOLVED.** The append race is still present. `action_log.py:87-93` reads head hash in one connection; `action_log.py:95-123` inserts later in a separate connection. `_SCHEMA` at `action_log.py:29-45` still has no `UNIQUE(agent_id, prev_hash)` or equivalent guard, and there is no transaction such as `BEGIN IMMEDIATE`.

5. **HIGH 5 — NOT RESOLVED.** `ActionRecord` is still only shallow-frozen. `types.py:57` sets `frozen=True`, but `types.py:66` still declares `payload: dict[str, Any]`. No Phase 1.5 change touched this file. Direct runtime check still allows `rec.payload["x"] = 2`. `tests/test_types.py:41-70` still does not assert deep immutability.

6. **HIGH 6 — NOT RESOLVED.** The protocol layer is unchanged and still narrow/stringly: `protocols/message_bus.py:5-13` uses `content: str` and returns `tuple[str, str]`; `protocols/policy_hook.py:23-24` is sync and takes untyped `context: dict`; `protocols/scenario_io.py:5-10` returns `tuple[dict, dict]`. No Phase 1.5 diff touched `clawsocialarena/protocols/`.

7. **MEDIUM 7 — PARTIALLY RESOLVED.** The important invariant tests were strengthened: `tests/test_runtime/test_runner.py:34-54` now asserts `terminal_predicate_passed`, pinned slot, opener logging, and `verify_chain()` for each agent; `tests/test_action_log.py:83-145` adds real tamper coverage; `tests/test_bus/test_audited.py:31-44` checks phase tagging. But `tests/test_protocols.py:4-6` is still a tautology.

8. **MEDIUM 8 — NOT RESOLVED.** The signature semantics mismatch remains. Spec text still says `"signature": "present iff level >= 3"` in `docs/superpowers/specs/2026-04-15-clawsocialarena-design.md:142`, while implementation still requires a signature only for `>= CROSS_AGENT_SIGNED` at `types.py:70-75`. `tests/test_types.py:57-70` still encodes the implementation behavior, not a clarified spec.

Local verification: `.venv/bin/pytest -q` -> `41 passed`.

**Final Verdict**

Phase 1.5 resolved the three critical blockers. It is ready to enter Phase 2, but not cleanly “done”: high issues #4, #5, and #6 remain open, with #4 the only one I would treat as a near-term must-fix before any concurrent logging/scoring work lands. #7 is improved but not fully closed, and #8 still needs spec/code reconciliation.
