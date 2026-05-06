# MSWM Transaction Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make gateway MSWM handling match the approved committed/tentative transaction design under blocks, rewrites, and concurrent gateway arrivals.

**Architecture:** The refactor lands in two stages. First, `Session` gets a per-session audit lock and owns message delivery enqueue through `send_outbound`, so the current mutate/revert behavior is serialized. Second, `MSWM` gets clone and transaction support, and `Session._record_action` uses explicit committed/tentative views instead of mutating committed MSWM before policy hooks.

**Tech Stack:** Python 3.11+, `asyncio`, `aiohttp`, Pydantic models, SQLite-backed `ActionLog`, `pytest`, `pytest-asyncio`.

---

## File Structure

- Modify `clawsocialarena/audit/mswm.py`: add `MSWM.clone()` and `MswmTransaction`.
- Modify `clawsocialarena/gateway/session.py`: add `audit_lock`, split locked/unlocked record helpers, add `send_outbound`, and later switch hook context to explicit MSWM transaction views.
- Modify `clawsocialarena/gateway/routes.py`: make `/send` delegate enqueue responsibility to `Session.send_outbound`.
- Modify `clawsocialarena/protocols/policy_hook.py`: document candidate-action hook semantics and context keys.
- Modify `clawsocialarena/audit/policies/mswm_aware.py`: prefer `mswm_tentative` while preserving the `mswm` alias.
- Modify `clawsocialarena/saf/scorers/policy_checkability.py`: replace local MSWM clone helper with `MSWM.clone()`.
- Modify `clawsocialarena/eval/leak_detector.py`: replace local MSWM clone helper with `MSWM.clone()`.
- Modify `tests/audit/test_mswm_model.py`: add clone and transaction unit tests.
- Modify `tests/audit/test_mswm_hook.py`: add explicit-context test for `MswmAwareHook`.
- Modify `tests/gateway/test_session_with_mswm.py`: add transaction-context, block-discard, and rewrite-rebuild tests.
- Modify `tests/gateway/test_enforcement.py`: add `send_outbound` enqueue and MCP lock-boundary tests.
- Optionally modify docstrings in tests touched above so they describe tentative MSWM rather than live pre-hook MSWM.

## Task 1: Add MSWM Clone And Transaction Unit Tests

**Files:**
- Modify: `tests/audit/test_mswm_model.py`
- Modify: `clawsocialarena/audit/mswm.py`

- [ ] **Step 1: Write failing tests for clone and transaction behavior**

Append these tests to `tests/audit/test_mswm_model.py` and update the import line to include `MswmTransaction` plus the action types used by the helper:

```python
from clawsocialarena.audit.mswm import MSWM, MswmTransaction, PeerModel
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)
```

Add this helper and tests near the bottom of the file:

```python
def _outbound(
    action_id: str,
    sender: str,
    recipient: str,
    mentioned: list[str],
) -> ActionRecord:
    return ActionRecord(
        action_id=action_id,
        prev_hash="0" * 64,
        agent_id=sender,
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-27T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={
            "recipient_id": recipient,
            "content": "hello",
            "mentioned_items": mentioned,
        },
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def test_mswm_clone_is_independent() -> None:
    mswm = MSWM()
    mswm.on_action(_outbound("act-1", "alice", "bob", ["z"]))

    cloned = mswm.clone()
    cloned.on_action(_outbound("act-2", "alice", "bob", ["private"]))

    assert mswm.known_items("bob") == {"z"}
    assert cloned.known_items("bob") == {"z", "private"}


def test_mswm_transaction_commit_returns_tentative_state() -> None:
    committed = MSWM()
    committed.on_action(_outbound("act-1", "alice", "bob", ["z"]))
    tx = MswmTransaction(committed)

    tx.apply_candidate(_outbound("act-2", "carol", "bob", ["y"]))

    assert committed.known_items("bob") == {"z"}
    assert tx.tentative.known_items("bob") == {"z", "y"}
    committed_after = tx.commit()
    assert committed_after.known_items("bob") == {"z", "y"}


def test_mswm_transaction_rebuild_and_discard() -> None:
    committed = MSWM()
    committed.on_action(_outbound("act-1", "alice", "bob", ["z"]))
    tx = MswmTransaction(committed)

    tx.apply_candidate(_outbound("act-2", "carol", "bob", ["bad"]))
    tx.rebuild(_outbound("act-2", "carol", "bob", ["safe"]))
    assert tx.tentative.known_items("bob") == {"z", "safe"}

    tx.discard()
    assert committed.known_items("bob") == {"z"}
    assert tx.tentative.known_items("bob") == {"z"}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/audit/test_mswm_model.py -q
```

Expected: FAIL with an import error or attribute error for `MswmTransaction` or `MSWM.clone`.

- [ ] **Step 3: Implement `MSWM.clone()` and `MswmTransaction`**

In `clawsocialarena/audit/mswm.py`, add this import near the top:

```python
from copy import deepcopy
```

Add this method inside `class MSWM`, after `pairs()`:

```python
    def clone(self) -> "MSWM":
        """Return an independent point-in-time copy of this MSWM."""

        cloned = MSWM()
        cloned.state = deepcopy(self.state)
        cloned.self_knowledge = deepcopy(self.self_knowledge)
        return cloned
```

Add this class after `class MSWM` or after all `MSWM` methods:

```python
class MswmTransaction:
    """Transaction-local committed and tentative MSWM views."""

    def __init__(self, committed: MSWM) -> None:
        self.committed = committed
        self.tentative = committed.clone()

    def apply_candidate(self, action: ActionRecord) -> None:
        self.tentative.on_action(action)

    def rebuild(self, action: ActionRecord) -> None:
        self.tentative = self.committed.clone()
        self.apply_candidate(action)

    def commit(self) -> MSWM:
        return self.tentative

    def discard(self) -> None:
        self.tentative = self.committed.clone()
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
pytest tests/audit/test_mswm_model.py -q
```

Expected: PASS.

- [ ] **Step 5: Approval-gated commit checkpoint**

Do not run this step unless the user has explicitly approved commits in the active session.

```bash
git add clawsocialarena/audit/mswm.py tests/audit/test_mswm_model.py
git commit -m "feat: add mswm transaction primitive"
```

## Task 2: Serialize Current Audit Writes And Move Send Enqueue Into Session

**Files:**
- Modify: `tests/gateway/test_enforcement.py`
- Modify: `clawsocialarena/gateway/session.py`
- Modify: `clawsocialarena/gateway/routes.py`

- [ ] **Step 1: Write failing session-level send and lock tests**

In `tests/gateway/test_enforcement.py`, add `asyncio` to imports:

```python
import asyncio
```

Add these tests after `test_baseline_ignores_hooks_entirely`:

```python
@pytest.mark.asyncio
async def test_send_outbound_enqueues_from_session_under_baseline(
    tmp_path: Path,
) -> None:
    session = Session.build(
        scenario_id="baseline-session-send",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",
        hooks=[RewriteMessageHook()],
    )

    outcome = await session.send_outbound(
        sender_id="alice",
        recipient_id="bob",
        content="hello x",
    )

    assert outcome.action_id is None
    assert outcome.blocked is False
    sender_id, delivered = session.inboxes["bob"].get_nowait()
    assert (sender_id, delivered) == ("alice", "hello x")
    assert session.action_log is None


@pytest.mark.asyncio
async def test_record_outbound_waits_for_audit_lock(tmp_path: Path) -> None:
    session = _passive_session(tmp_path, [])
    await session.audit_lock.acquire()

    try:
        task = asyncio.create_task(
            session.record_outbound(
                sender_id="alice",
                recipient_id="bob",
                content="hello",
                mentioned_items=["z"],
            )
        )
        await asyncio.sleep(0)
        assert task.done() is False
    finally:
        session.audit_lock.release()

    outcome = await task
    assert outcome.blocked is False
    assert session.mswm.known_items("bob") == {"z"}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/gateway/test_enforcement.py::test_send_outbound_enqueues_from_session_under_baseline tests/gateway/test_enforcement.py::test_record_outbound_waits_for_audit_lock -q
```

Expected: FAIL because `Session.send_outbound` and `Session.audit_lock` do not exist.

- [ ] **Step 3: Add `audit_lock`, `_record_action_unlocked`, and `send_outbound`**

In `clawsocialarena/gateway/session.py`, add the field near `mswm`:

```python
    audit_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
```

Change `_record_action` into a lock wrapper and move the current body into `_record_action_unlocked`:

```python
    async def _record_action(
        self,
        *,
        agent_id: str,
        action_type: ActionType,
        payload: dict,
        id_prefix: str,
        hook_target_content: str | None,
        source_action_ids: list[str] | None = None,
    ) -> RecordOutcome:
        async with self.audit_lock:
            return await self._record_action_unlocked(
                agent_id=agent_id,
                action_type=action_type,
                payload=payload,
                id_prefix=id_prefix,
                hook_target_content=hook_target_content,
                source_action_ids=source_action_ids,
            )

    async def _record_action_unlocked(
        self,
        *,
        agent_id: str,
        action_type: ActionType,
        payload: dict,
        id_prefix: str,
        hook_target_content: str | None,
        source_action_ids: list[str] | None = None,
    ) -> RecordOutcome:
        """Shared helper. Caller must hold ``self.audit_lock``."""

        # Move the existing _record_action body here unchanged for this task.
```

Add this public method near `record_outbound`:

```python
    async def send_outbound(
        self,
        *,
        sender_id: str,
        recipient_id: str,
        content: str,
        source_action_ids: list[str] | None = None,
        mentioned_items: list[str] | None = None,
    ) -> RecordOutcome:
        """Record and enqueue an outbound message in one audit transaction."""

        async with self.audit_lock:
            if self.condition == AuditCondition.BASELINE or self.action_log is None:
                inbox = self.ensure_inbox(recipient_id)
                await inbox.put((sender_id, content))
                return RecordOutcome()

            payload: dict = {"recipient_id": recipient_id, "content": content}
            if mentioned_items:
                payload["mentioned_items"] = list(mentioned_items)

            outcome = await self._record_action_unlocked(
                agent_id=sender_id,
                action_type=ActionType.OUTBOUND_MESSAGE,
                payload=payload,
                id_prefix="act",
                hook_target_content=content,
                source_action_ids=source_action_ids,
            )
            if outcome.blocked:
                return outcome

            delivered = (
                outcome.rewritten_content
                if outcome.rewritten_content is not None
                else content
            )
            inbox = self.ensure_inbox(recipient_id)
            await inbox.put((sender_id, delivered))
            return outcome
```

Keep `record_outbound` as record-only. It should still call `_record_action`, not enqueue.

- [ ] **Step 4: Move route enqueue into `Session.send_outbound`**

In `clawsocialarena/gateway/routes.py`, replace the call and enqueue block in `send` with:

```python
    session = _get_session(request)
    outcome = await session.send_outbound(
        sender_id=sender_id,
        recipient_id=recipient_id,
        content=content,
        source_action_ids=sources,
        mentioned_items=mentioned,
    )
    if outcome.blocked:
        return web.json_response({"action_id": None, "blocked": True})

    return web.json_response({"action_id": outcome.action_id, "blocked": False})
```

- [ ] **Step 5: Run targeted tests**

Run:

```bash
pytest tests/gateway/test_enforcement.py::test_send_outbound_enqueues_from_session_under_baseline tests/gateway/test_enforcement.py::test_record_outbound_waits_for_audit_lock tests/gateway/test_enforcement.py::test_passive_leaves_original_in_inbox_but_logs_policy_decision tests/gateway/test_enforcement.py::test_enforce_puts_rewritten_content_in_inbox tests/gateway/test_enforcement.py::test_enforce_block_suppresses_inbox_and_returns_blocked_true -q
```

Expected: PASS.

- [ ] **Step 6: Approval-gated commit checkpoint**

Do not run this step unless the user has explicitly approved commits in the active session.

```bash
git add clawsocialarena/gateway/session.py clawsocialarena/gateway/routes.py tests/gateway/test_enforcement.py
git commit -m "fix: serialize gateway audit transactions"
```

## Task 3: Update Hook Context Contract And MSWM-Aware Hook Preference

**Files:**
- Modify: `tests/audit/test_mswm_hook.py`
- Modify: `clawsocialarena/protocols/policy_hook.py`
- Modify: `clawsocialarena/audit/policies/mswm_aware.py`

- [ ] **Step 1: Write failing explicit-context test**

In `tests/audit/test_mswm_hook.py`, update imports:

```python
from clawsocialarena.audit.mswm import MSWM
from clawsocialarena.protocols import PolicyVerdict
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    AuditCondition,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)
```

Add this helper and test near `_vignette_invariants`:

```python
def _record(
    action_id: str,
    sender: str,
    recipient: str,
    mentioned: list[str],
) -> ActionRecord:
    return ActionRecord(
        action_id=action_id,
        prev_hash="0" * 64,
        agent_id=sender,
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-27T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={
            "recipient_id": recipient,
            "content": "...",
            "mentioned_items": mentioned,
        },
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def test_mswm_aware_hook_prefers_tentative_context_key() -> None:
    committed = MSWM()
    committed.on_action(_record("act-1", "alice", "carol", ["med_x"]))
    tentative = committed.clone()
    tentative.on_action(_record("act-2", "bob", "carol", ["condition_y"]))

    hook = MswmAwareHook(_vignette_invariants())
    decision = hook.evaluate(
        action=_record("act-2", "bob", "carol", ["condition_y"]),
        context={
            "mswm_committed": committed,
            "mswm_tentative": tentative,
        },
    )

    assert decision.verdict == PolicyVerdict.BLOCK
    assert decision.policy_id == "carol-no-joint"
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
pytest tests/audit/test_mswm_hook.py::test_mswm_aware_hook_prefers_tentative_context_key -q
```

Expected: FAIL because `MswmAwareHook` only reads `context["mswm"]`.

- [ ] **Step 3: Update hook docs and implementation**

In `clawsocialarena/protocols/policy_hook.py`, replace the class docstring with:

```python
    """Hook that evaluates a candidate ActionRecord and returns a decision.

    ``action`` is a proposed record, not yet a delivered fact. Gateway
    callers pass context keys for runtime state:

    - ``mswm_tentative``: committed MSWM plus the candidate action.
    - ``mswm_committed``: delivered / accepted actions only.
    - ``mswm``: backward-compatible alias for ``mswm_tentative``.
    - ``candidate_action_id``: id minted for the candidate target action.

    Hooks may additionally declare a ``hook_kind`` class attribute to scope
    which action types they fire on.
    """
```

In `clawsocialarena/audit/policies/mswm_aware.py`, change the context read to:

```python
        mswm = context.get("mswm_tentative") or context.get("mswm")
```

Update that module's top docstring so it says the hook evaluates tentative MSWM supplied by the gateway context.

- [ ] **Step 4: Run hook tests**

Run:

```bash
pytest tests/audit/test_mswm_hook.py -q
```

Expected: PASS.

- [ ] **Step 5: Approval-gated commit checkpoint**

Do not run this step unless the user has explicitly approved commits in the active session.

```bash
git add clawsocialarena/protocols/policy_hook.py clawsocialarena/audit/policies/mswm_aware.py tests/audit/test_mswm_hook.py
git commit -m "docs: define policy hook transaction context"
```

## Task 4: Switch Session To Explicit MSWM Transactions

**Files:**
- Modify: `tests/gateway/test_session_with_mswm.py`
- Modify: `clawsocialarena/gateway/session.py`

- [ ] **Step 1: Write failing transaction-context tests**

In `tests/gateway/test_session_with_mswm.py`, add these tests before the bottom import:

```python
@pytest.mark.asyncio
async def test_hook_context_exposes_committed_and_tentative_mswm(
    tmp_path: Path,
) -> None:
    seen: list[tuple[set[str], set[str], bool]] = []

    class InspectContext:
        hook_kind = "message"

        def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
            committed = context["mswm_committed"]
            tentative = context["mswm_tentative"]
            seen.append(
                (
                    committed.known_items("bob"),
                    tentative.known_items("bob"),
                    context["mswm"] is tentative,
                )
            )
            return PolicyDecision(verdict=PolicyVerdict.ALLOW)

    session = Session.build(
        scenario_id="mswm-context-views",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "passive.db",
        hooks=[InspectContext()],
    )

    await session.record_outbound(
        sender_id="alice",
        recipient_id="bob",
        content="hi",
        mentioned_items=["z"],
    )

    assert seen == [(set(), {"z"}, True)]
    assert session.mswm.known_items("bob") == {"z"}


@pytest.mark.asyncio
async def test_block_discards_tentative_mswm_without_revert_call(
    tmp_path: Path,
) -> None:
    class BlockAll:
        hook_kind = "message"

        def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
            return PolicyDecision(verdict=PolicyVerdict.BLOCK, policy_id="bl")

    session = Session.build(
        scenario_id="block-no-revert",
        condition=AuditCondition.ENFORCE,
        db_path=tmp_path / "enforce.db",
        hooks=[BlockAll()],
    )

    def fail_revert(action: ActionRecord) -> None:
        raise AssertionError("revert_action should not be used by transaction flow")

    session.mswm.revert_action = fail_revert  # type: ignore[method-assign]

    outcome = await session.record_outbound(
        sender_id="alice",
        recipient_id="bob",
        content="hi",
        mentioned_items=["z"],
    )

    assert outcome.blocked is True
    assert session.mswm.known_items("bob") == set()


@pytest.mark.asyncio
async def test_rewrite_rebuilds_tentative_before_later_hooks(
    tmp_path: Path,
) -> None:
    observed: list[set[str]] = []

    class RewriteMentioned:
        hook_kind = "message"

        def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
            return PolicyDecision(
                verdict=PolicyVerdict.REWRITE,
                rewritten_content=action.payload["content"],
                rewritten_mentioned_items=["safe_item"],
                policy_id="rewrite-mentioned",
            )

    class InspectAfterRewrite:
        hook_kind = "message"

        def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
            observed.append(context["mswm_tentative"].known_items("bob"))
            return PolicyDecision(verdict=PolicyVerdict.ALLOW)

    session = Session.build(
        scenario_id="rewrite-rebuilds-tentative",
        condition=AuditCondition.ENFORCE,
        db_path=tmp_path / "enforce.db",
        hooks=[RewriteMentioned(), InspectAfterRewrite()],
    )

    outcome = await session.record_outbound(
        sender_id="alice",
        recipient_id="bob",
        content="hi",
        mentioned_items=["safe_item", "forbidden_item"],
    )

    assert outcome.blocked is False
    assert observed == [{"safe_item"}]
    assert session.mswm.known_items("bob") == {"safe_item"}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
pytest tests/gateway/test_session_with_mswm.py::test_hook_context_exposes_committed_and_tentative_mswm tests/gateway/test_session_with_mswm.py::test_block_discards_tentative_mswm_without_revert_call tests/gateway/test_session_with_mswm.py::test_rewrite_rebuilds_tentative_before_later_hooks -q
```

Expected: FAIL because context keys are missing and current block handling calls `revert_action`.

- [ ] **Step 3: Import and create MSWM transactions in `Session`**

In `clawsocialarena/gateway/session.py`, change the MSWM import:

```python
from clawsocialarena.audit.mswm import MSWM, MswmTransaction
```

Inside `_record_action_unlocked`, after `initial_provisional` is built, replace the direct MSWM mutation:

```python
        tx = MswmTransaction(self.mswm)
        tx.apply_candidate(initial_provisional)
```

Remove:

```python
        self.mswm.on_action(initial_provisional)
```

When calling hooks, replace the context with:

```python
                context = {
                    "mswm": tx.tentative,
                    "mswm_tentative": tx.tentative,
                    "mswm_committed": tx.committed,
                    "candidate_action_id": action_id,
                }
                decision: PolicyDecision = hook.evaluate(
                    action=provisional, context=context
                )
```

- [ ] **Step 4: Rebuild transaction state after ENFORCE rewrites**

After `current_content` and `current_mentioned` are updated for an ENFORCE rewrite, rebuild the candidate payload and transaction before the next hook runs:

```python
                        rewritten_payload = dict(payload)
                        if hook_target_content is not None:
                            content_key = _content_key_for_action(action_type)
                            if content_key is not None:
                                rewritten_payload[content_key] = current_content
                        if current_mentioned is not None:
                            rewritten_payload["mentioned_items"] = list(
                                current_mentioned
                            )
                        rewritten_provisional = ActionRecord(
                            action_id=action_id,
                            prev_hash=self.action_log.head_hash(agent_id),
                            agent_id=agent_id,
                            action_type=action_type,
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            execution_phase=ExecutionPhase.NOMINAL,
                            social_phase=social_phase,
                            payload=rewritten_payload,
                            integrity_level=IntegrityLevel.HASH_CHAINED,
                            source_action_ids=sources,
                        )
                        tx.rebuild(rewritten_provisional)
```

- [ ] **Step 5: Commit or discard transaction**

In the block branch, remove the revert call and discard the transaction:

```python
        if blocked:
            tx.discard()
            _ = block_decision
            return RecordOutcome(action_id=None, blocked=True)
```

After final action rows and cassette are written, assign committed state:

```python
        self.mswm = tx.commit()
```

Remove the old rewrite reconciliation block that calls `self.mswm.revert_action(initial_provisional)` and `self.mswm.on_action(record)`. The transaction has already been rebuilt after rewrites.

- [ ] **Step 6: Run transaction tests**

Run:

```bash
pytest tests/gateway/test_session_with_mswm.py -q
```

Expected: PASS.

- [ ] **Step 7: Approval-gated commit checkpoint**

Do not run this step unless the user has explicitly approved commits in the active session.

```bash
git add clawsocialarena/gateway/session.py tests/gateway/test_session_with_mswm.py
git commit -m "feat: use tentative mswm transactions in session"
```

## Task 5: Preserve Route Semantics And Tool Lock Boundaries

**Files:**
- Modify: `tests/gateway/test_enforcement.py`
- Modify: `clawsocialarena/gateway/routes.py`
- Modify: `clawsocialarena/gateway/session.py`

- [ ] **Step 1: Write MCP lock-boundary test**

Append this test to `tests/gateway/test_enforcement.py` near the MCP tests:

```python
@pytest.mark.asyncio
async def test_mcp_dispatch_does_not_hold_audit_lock_during_tool_execution(
    tmp_path: Path,
) -> None:
    session = _enforce_session(tmp_path, [])

    def inspect_lock(**_: object) -> dict:
        return {"audit_lock_held": session.audit_lock.locked()}

    session.mcp_host.register("inspect_lock", inspect_lock)
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/mcp/inspect_lock",
            json={"agent_id": "alice", "arguments": {}},
        )
        assert resp.status == 200
        body = await resp.json()

    assert body["blocked"] is False
    assert body["observation"] == {"audit_lock_held": False}
```

- [ ] **Step 2: Run route regression tests**

Run:

```bash
pytest tests/gateway/test_enforcement.py::test_mcp_dispatch_does_not_hold_audit_lock_during_tool_execution tests/gateway/test_send_recv.py tests/gateway/test_side_channels.py -q
```

Expected before Task 5 implementation: the new MCP test should PASS if Task 2 avoided holding the lock through dispatch. If it fails, inspect `routes.mcp_dispatch` and move any lock-bearing call so only `record_tool_call` and `record_tool_observation` acquire locks.

- [ ] **Step 3: Keep `/send` response shape stable**

Confirm `clawsocialarena/gateway/routes.py` returns the same shape:

```python
    if outcome.blocked:
        return web.json_response({"action_id": None, "blocked": True})

    return web.json_response({"action_id": outcome.action_id, "blocked": False})
```

Do not include delivered content in the `/send` response. Existing plugin callers expect only `action_id` and `blocked`.

- [ ] **Step 4: Run route tests**

Run:

```bash
pytest tests/gateway/test_enforcement.py tests/gateway/test_send_recv.py tests/gateway/test_side_channels.py -q
```

Expected: PASS.

- [ ] **Step 5: Approval-gated commit checkpoint**

Do not run this step unless the user has explicitly approved commits in the active session.

```bash
git add clawsocialarena/gateway/routes.py clawsocialarena/gateway/session.py tests/gateway/test_enforcement.py
git commit -m "test: preserve gateway route transaction boundaries"
```

## Task 6: Replace Duplicate MSWM Clone Helpers

**Files:**
- Modify: `clawsocialarena/saf/scorers/policy_checkability.py`
- Modify: `clawsocialarena/eval/leak_detector.py`

- [ ] **Step 1: Replace policy-checkability clone helper**

In `clawsocialarena/saf/scorers/policy_checkability.py`, change:

```python
snaps.append(_clone_mswm(m))
```

to:

```python
snaps.append(m.clone())
```

Change the later append in the same function the same way:

```python
snaps.append(m.clone())
```

Remove the local `_clone_mswm` function and its `deepcopy` import.

- [ ] **Step 2: Replace leak-detector clone helper**

In `clawsocialarena/eval/leak_detector.py`, change:

```python
preroll[rec.action_id] = _clone_mswm(rolling)
```

to:

```python
preroll[rec.action_id] = rolling.clone()
```

Remove the local `_clone_mswm` function and its `deepcopy` import.

- [ ] **Step 3: Run affected tests**

Run:

```bash
pytest tests/test_saf/test_policy_checkability_mswm.py tests/test_eval/test_eval_runner_inferential_policy.py tests/test_eval/test_eval_runner_v2.py -q
```

Expected: PASS.

- [ ] **Step 4: Approval-gated commit checkpoint**

Do not run this step unless the user has explicitly approved commits in the active session.

```bash
git add clawsocialarena/saf/scorers/policy_checkability.py clawsocialarena/eval/leak_detector.py
git commit -m "refactor: share mswm clone helper"
```

## Task 7: Refresh Wording And Run Full Verification

**Files:**
- Modify: `clawsocialarena/audit/mswm.py`
- Modify: `clawsocialarena/gateway/session.py`
- Modify: `tests/gateway/test_session_with_mswm.py`
- Modify: `clawsocialarena/audit/policies/mswm_aware.py`

- [ ] **Step 1: Update stale wording**

Search:

```bash
rg -n "BEFORE policy hooks|before policy hooks|provisional MSWM update|revert the provisional|live MSWM state|already applied" clawsocialarena tests
```

Replace stale wording in docstrings and comments with the approved terms:

```text
candidate action
tentative MSWM
committed MSWM
pre-commit policy hook
transaction-local state
```

Keep mentions of `revert_action` inside `MSWM.revert_action` if tests or attribution still use it directly. The function can remain for compatibility and offline diagnostic fixtures.

- [ ] **Step 2: Run focused regression suite**

Run:

```bash
pytest tests/audit/test_mswm_model.py tests/audit/test_mswm_hook.py tests/gateway/test_session_with_mswm.py tests/gateway/test_enforcement.py tests/gateway/test_send_recv.py tests/gateway/test_side_channels.py -q
```

Expected: PASS.

- [ ] **Step 3: Run broader Python suite**

Run:

```bash
pytest -q
```

Expected: PASS, with the repository's existing skipped tests unchanged.

- [ ] **Step 4: Run static checks**

Run:

```bash
ruff check .
mypy clawsocialarena
```

Expected: both commands exit 0.

- [ ] **Step 5: Check Markdown and changed-file whitespace**

Run:

```bash
git diff --check
```

Expected: no output and exit 0.

- [ ] **Step 6: Approval-gated final commit checkpoint**

Do not run this step unless the user has explicitly approved commits in the active session.

```bash
git add clawsocialarena/audit/mswm.py clawsocialarena/gateway/session.py clawsocialarena/gateway/routes.py clawsocialarena/protocols/policy_hook.py clawsocialarena/audit/policies/mswm_aware.py clawsocialarena/saf/scorers/policy_checkability.py clawsocialarena/eval/leak_detector.py tests/audit/test_mswm_model.py tests/audit/test_mswm_hook.py tests/gateway/test_session_with_mswm.py tests/gateway/test_enforcement.py
git commit -m "feat: align mswm runtime with transaction semantics"
```

## Self-Review Checklist

- Spec coverage: Tasks 1 and 4 implement explicit MSWM transactions. Task 2 implements per-session serialization and session-owned delivery enqueue. Task 3 implements hook context compatibility. Task 5 confirms route behavior and tool dispatch lock boundaries. Task 6 removes clone duplication. Task 7 updates stale wording and verifies the refactor.
- Type consistency: The plan uses `MswmTransaction`, `MSWM.clone()`, `Session.audit_lock`, `Session.send_outbound`, `mswm_tentative`, `mswm_committed`, and `candidate_action_id` consistently.
- Public API stability: `/send`, `/tool_call`, `/memory_write`, and `/mcp/{tool_name}` response shapes remain unchanged.
- Commit safety: Every commit step is approval-gated because this repository forbids commits without explicit user approval.
