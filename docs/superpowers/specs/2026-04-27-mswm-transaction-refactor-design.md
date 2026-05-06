# MSWM Transaction Refactor Design

## 1. Purpose

The updated ClawSocialArena v2 spec defines policy hooks as pre-commit candidate evaluators. A hook must be able to inspect the epistemic consequences of the candidate action before delivery, but blocked actions must not leave committed MSWM state behind. The current code approximates this by mutating `Session.mswm` before hooks run, then reverting on block or rewrite. That behavior is sequentially correct for the existing tests, but it is unsafe under concurrent gateway arrivals because another in-flight hook can observe the provisional state.

This refactor brings the codebase into line with the updated spec in two phases. Phase 1 adds transaction serialization around the current behavior so no concurrent request can observe provisional MSWM state. Phase 2 replaces the implicit mutate/revert mechanism with an explicit MSWM transaction view so committed and tentative state are visible in the API and in tests.

## 2. Current Mismatch

The main mismatch is in `clawsocialarena/gateway/session.py`. `Session._record_action` currently builds a provisional `ActionRecord`, applies it directly to `self.mswm`, runs matching hooks with `context={"mswm": self.mswm}`, then reverts or reconciles MSWM if an ENFORCE hook blocks or rewrites the action. This lets MSWM-aware hooks catch the current message that completes an inference, which is required. The problem is that `self.mswm` is shared session state.

The second mismatch is the method boundary. The spec says the audit transaction covers delivery enqueue for messages, but `routes.send` currently calls `session.record_outbound(...)` and only afterward enqueues the delivered content. That leaves the log / MSWM commit and inbox delivery split across two layers.

The third mismatch is vocabulary. `PolicyHook` and `MswmAwareHook` docs still describe hooks as seeing live MSWM state rather than a candidate-state view. Tests also use names such as `test_hook_sees_mswm_context_with_current_action_already_applied`, which is behaviorally close but does not say that the view is tentative.

## 3. Refactor Strategy

### 3.1 Phase 1: Serialize Audit Transactions

Add a per-session `asyncio.Lock`, for example `audit_lock`, owned by `Session`. Every audited write path should execute its critical section under this lock. The lock should cover candidate action construction, policy-hook evaluation, policy-decision logging, final action append, committed MSWM update, cassette write, and any message delivery enqueue.

For message sends, the clean boundary is a new `Session.send_outbound(...)` method that wraps `record_outbound(...)` plus inbox enqueue. `routes.send` should delegate to that method and only format the HTTP response. This keeps the gateway route thin and ensures the spec's transaction boundary lives in the session object, not across route and session code.

For tool calls and memory writes, the same lock can guard `_record_action`. MCP dispatch itself should not be held under the audit lock because the external tool call can be slow and the policy decision point is the pre-tool `TOOL_CALL` record. The lock should cover `record_tool_call`; if it allows the call, the route can dispatch the MCP tool afterward, then call `record_tool_observation`, which is a separate audited action with its own lock acquisition.

Phase 1 intentionally preserves the current mutate/revert implementation. The important safety property is that no other audited request can read `self.mswm` while it contains another action's provisional update.

### 3.2 Phase 2: Add Explicit MSWM Transactions

Introduce an MSWM transaction abstraction with this conceptual API:

```python
class MswmTransaction:
    committed: MSWM
    tentative: MSWM

    def apply_candidate(self, action: ActionRecord) -> None: ...
    def rebuild(self, action: ActionRecord) -> None: ...
    def commit(self) -> None: ...
    def discard(self) -> None: ...
```

The transaction starts from a clone of committed `Session.mswm`. The candidate action is applied to `transaction.tentative`, not to `Session.mswm`. Hooks receive:

```python
{
    "mswm": transaction.tentative,
    "mswm_tentative": transaction.tentative,
    "mswm_committed": transaction.committed,
    "candidate_action_id": action_id,
}
```

The `"mswm"` key remains a backward-compatible alias for existing hooks. New code and tests should use `mswm_tentative` and `mswm_committed` because they state the semantics explicitly.

On ALLOW, the final action is appended and the tentative MSWM is committed to `Session.mswm`. On REWRITE, the candidate payload is changed, the transaction rebuilds tentative state from committed state plus the rewritten candidate, and later hooks see the rewritten tentative state. On BLOCK, the policy-decision row is logged and the transaction is discarded. The target action is not appended and committed MSWM is unchanged.

### 3.3 Keep the Lock After Overlay

Even after Phase 2, keep the per-session audit lock. The overlay prevents provisional-state reads, but the lock still provides deterministic action ordering, keeps hash-chain heads stable across candidate construction and append, and makes the sequence of policy-decision rows reproducible. The overlay improves correctness and clarity; the lock preserves ordered audit semantics.

## 4. Component Changes

### 4.1 `clawsocialarena/audit/mswm.py`

Add a single official clone helper, for example `MSWM.clone() -> MSWM`, instead of duplicating deep-copy helpers in scoring and evaluation modules. The helper should deep-copy `state` and `self_knowledge`. Existing private helpers in `saf/scorers/policy_checkability.py` and `eval/leak_detector.py` can later delegate to it.

Add `MswmTransaction` either in this module or in a small neighboring module such as `audit/mswm_transaction.py`. Keeping it near `MSWM` is better because it owns MSWM copy and commit semantics.

### 4.2 `clawsocialarena/gateway/session.py`

Add `audit_lock: asyncio.Lock` as a session field. Because locks should be created per instance, use `field(default_factory=asyncio.Lock)`.

Split `_record_action` into smaller internal steps during Phase 2:

- Build candidate action.
- Build policy context.
- Evaluate matching hooks.
- Apply block / rewrite / allow decision.
- Append policy-decision rows.
- Append final action rows.
- Commit or discard MSWM transaction.

This split keeps the existing public methods stable while making the transaction flow testable.

Add `send_outbound(...) -> RecordOutcome`. The method should record the outbound action and enqueue the final delivered content while holding the session audit lock. `RecordOutcome` can keep its current fields; `rewritten_content` remains useful for tests and callers that need to know whether ENFORCE changed the payload. Under ENFORCE block, `send_outbound` skips enqueue. Under BASELINE, it still enqueues the original content and returns `action_id=None, blocked=False`.

### 4.3 `clawsocialarena/gateway/routes.py`

Move message-delivery responsibility out of `routes.send` and into `Session.send_outbound(...)`. The route should parse / validate JSON, call the session method, and return the response body. This removes the split transaction boundary.

Tool routes should not hold the audit lock during MCP dispatch. They should continue to call `record_tool_call`, perform dispatch if not blocked, then call `record_tool_observation`.

### 4.4 `clawsocialarena/protocols/policy_hook.py`

Update docstrings so `PolicyHook.evaluate` is defined as evaluating a candidate action. The `context` contract should name `mswm_tentative`, `mswm_committed`, and the backward-compatible `mswm` alias. No signature change is needed.

### 4.5 `clawsocialarena/audit/policies/mswm_aware.py`

Update docs to say the hook consults tentative MSWM. The implementation should read `context.get("mswm_tentative") or context.get("mswm")`, preserving compatibility while preferring the explicit transaction key. Tests should verify that `mswm_tentative` is sufficient.

## 5. Data Flow

The target message-send flow is:

```text
routes.send
  validate request
  session.send_outbound
    acquire session.audit_lock
    if baseline:
      enqueue original content
      return action_id=None, blocked=False
    build candidate action
    start MSWM transaction
    apply candidate to tentative MSWM
    run hooks with candidate + tentative context
    append policy_decision rows
    if block:
      discard transaction
      return blocked=True
    if rewrite:
      rebuild candidate payload
      rebuild tentative MSWM
    append final action to primary log, shadow log, cassette
    commit tentative MSWM
    enqueue delivered content
    return action_id, blocked=False, rewritten_content if any
  format HTTP response
```

The target memory / tool decision flow is the same through the policy-decision point, except there is no inbox enqueue. Tool dispatch remains outside the pre-tool audit transaction.

## 6. Error Handling

If a policy hook raises, the transaction should discard tentative MSWM state, avoid appending the target action, skip delivery / execution, and propagate the exception so the route fails with a server error. The implementation should not silently convert hook crashes into block decisions, because that would hide infrastructure bugs as policy outcomes.

If final action append fails after policy-decision rows were appended, the transaction must not commit MSWM or enqueue delivery. The log may contain policy-decision evidence for a target that never committed, which is consistent with a failed or blocked target. The route should surface the append failure rather than delivering an unlogged message.

If enqueue fails after final action append and MSWM commit, the system has committed a delivered action that was not actually delivered. To avoid this split-brain case, Phase 1 should move enqueue under the same session method and place enqueue before the final return. If queue enqueue can raise in practice, the implementation should append a delivery-failure policy or system record in a later phase. For the current in-memory `asyncio.Queue`, enqueue failure is not expected.

## 7. Tests

Phase 1 tests:

- `test_audit_lock_serializes_concurrent_mswm_hooks`: use two concurrent sends and a hook that blocks inside `evaluate` until both requests are in flight. Assert the second hook does not observe the first request's provisional MSWM until the first transaction finishes.
- `test_send_outbound_enqueues_under_session_transaction`: assert route-level send no longer performs enqueue directly and blocked ENFORCE sends leave inbox unchanged.
- Existing block and rewrite tests should continue to pass.

Phase 2 tests:

- `test_hook_context_exposes_committed_and_tentative_mswm`: inside a hook, assert `mswm_committed` lacks the candidate item while `mswm_tentative` contains it.
- `test_block_discards_tentative_mswm_without_revert`: blocked action leaves committed MSWM unchanged without relying on `revert_action`.
- `test_rewrite_rebuilds_tentative_before_later_hooks`: first hook rewrites `mentioned_items`; second hook asserts tentative MSWM reflects the rewritten items only.
- `test_context_mswm_alias_is_tentative`: backward-compatible `context["mswm"]` points to the tentative view.

Regression tests:

- Existing MSWM-aware inferential policy tests still block the message that completes an inference.
- Passive rewrite still logs the rewrite verdict but commits the original action and original MSWM.
- Enforce rewrite commits only rewritten `mentioned_items`.
- Action log hash chains remain valid under concurrent sends.

## 8. Migration Notes

The refactor should not change the public HTTP API. `/send`, `/tool_call`, `/memory_write`, and `/mcp/{tool_name}` response shapes stay the same.

Existing hooks remain source-compatible because `PolicyHook.evaluate` keeps the same signature and `context["mswm"]` remains available. New hooks should use `context["mswm_tentative"]` and `context["mswm_committed"]`.

Offline scoring and replay should continue to rebuild MSWM from committed action logs only. Blocked targets are represented by `policy_decision` rows, not by committed target actions, so they should not update replayed committed MSWM.

## 9. Acceptance Criteria

The refactor is complete when:

- No audited request can observe another request's tentative MSWM state.
- Policy hooks can inspect both committed and tentative MSWM views.
- Blocked actions do not change committed MSWM.
- Rewritten actions commit MSWM state for the rewritten payload only.
- Message delivery enqueue is part of the session-level send transaction.
- Existing public HTTP response shapes are unchanged.
- Tests cover block, rewrite, tentative-vs-committed context, and concurrent send ordering.

## 10. Benchmark Construction Dependency

The benchmark construction pipeline should treat this transaction behavior as part of the run-readiness contract. A scenario run is not ready for benchmark scoring if a blocked action leaves committed MSWM state behind, if concurrent arrivals can reorder policy decisions without a stable log order, or if message delivery happens outside the audited transaction. These cases would corrupt the evidence used for privacy, governance, and SAF metrics.

The May 5, 2026 smoke checkpoint exercised the current gateway path across 80 paid LLM-naturalized Docker simulations. Those runs validate the end-to-end path at smoke scale, but full scale-out should keep checking that blocked actions have no committed MSWM footprint and that every scorecard can be replayed from committed action logs, policy-decision rows, cassettes, and final resource state.
