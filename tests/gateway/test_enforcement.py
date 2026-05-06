"""Tests for gateway Session enforce/passive/baseline semantics (Phase A.5).

The Session now owns the hook-dispatch / shadow-double-write /
policy-decision-emission pipeline that previously lived in
``clawsocialarena/bus/audited.py``. These tests pin down the observable
behavior per audit condition:

- BASELINE: hooks are not evaluated even when they are somehow attached,
  no POLICY_DECISION rows are written, and the returned
  :class:`~clawsocialarena.gateway.session.RecordOutcome` never carries a
  rewrite or a block. The Session.build factory drops any hooks handed to
  it under BASELINE, but this file also constructs a hand-built Session
  with hooks to confirm the per-action gate.
- PASSIVE: hook verdicts land as POLICY_DECISION rows, but the original
  content reaches the inbox and the persisted OUTBOUND_MESSAGE row carries
  the ORIGINAL content. ``blocked`` is always False.
- ENFORCE: rewrite verdicts replace both the inbox content AND the
  persisted OUTBOUND_MESSAGE content; block verdicts set ``blocked=True``,
  suppress the inbox enqueue, and omit the OUTBOUND_MESSAGE row (the
  evidence survives only via POLICY_DECISION).

Tool-kind and memory-kind coverage is included to exercise the
``_HOOK_KIND_FOR_ACTION`` routing: a tool-kind block skips MCP dispatch,
and a memory-kind rewrite replaces the persisted memory_write content.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from clawsocialarena.gateway.server import build_app
from clawsocialarena.gateway.session import Session
from clawsocialarena.protocols import PolicyDecision, PolicyVerdict
from clawsocialarena.types import ActionRecord, ActionType, AuditCondition


class RewriteMessageHook:
    """Rewrites ``x`` to ``y`` on outbound messages. Default hook_kind='message'."""

    hook_kind = "message"

    def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
        content = action.payload.get("content", "")
        if "x" in content:
            return PolicyDecision(
                verdict=PolicyVerdict.REWRITE,
                rewritten_content=content.replace("x", "y"),
                reason="map x to y",
                policy_id="xy-map",
            )
        return PolicyDecision(verdict=PolicyVerdict.ALLOW)


class BlockToolHook:
    """Blocks any tool_call whose name contains ``danger``."""

    hook_kind = "tool"

    def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
        if "danger" in action.payload.get("tool_name", ""):
            return PolicyDecision(
                verdict=PolicyVerdict.BLOCK,
                reason="unsafe tool",
                policy_id="no-danger",
            )
        return PolicyDecision(verdict=PolicyVerdict.ALLOW)


class RewriteMemoryHook:
    """Rewrites memory_write content by appending a redaction marker."""

    hook_kind = "memory"

    def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
        content = action.payload.get("content", "")
        if "secret" in content:
            return PolicyDecision(
                verdict=PolicyVerdict.REWRITE,
                rewritten_content=content.replace("secret", "[redacted]"),
                reason="redact secrets",
                policy_id="mem-dlp",
            )
        return PolicyDecision(verdict=PolicyVerdict.ALLOW)


def _passive_session(tmp_path: Path, hooks) -> Session:
    return Session.build(
        scenario_id="a5-enforce-passive",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "passive.db",
        hooks=hooks,
    )


def _enforce_session(tmp_path: Path, hooks) -> Session:
    return Session.build(
        scenario_id="a5-enforce-enforce",
        condition=AuditCondition.ENFORCE,
        db_path=tmp_path / "enforce.db",
        hooks=hooks,
    )


@pytest.mark.asyncio
async def test_passive_leaves_original_in_inbox_but_logs_policy_decision(
    tmp_path: Path,
) -> None:
    """PASSIVE: inbox carries the ORIGINAL content; a POLICY_DECISION still logs."""

    session = _passive_session(tmp_path, [RewriteMessageHook()])
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/send",
            json={"sender_id": "alice", "recipient_id": "bob", "content": "hello x"},
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["blocked"] is False
        assert isinstance(body["action_id"], str)

        recv = await client.post("/recv", json={"recipient_id": "bob"})
        assert recv.status == 200
        delivered = await recv.json()
        assert delivered == {"sender_id": "alice", "content": "hello x"}

    assert session.action_log is not None
    rows = session.action_log.read_all()
    action_types = [r.action_type for r in rows]
    assert ActionType.POLICY_DECISION in action_types
    assert ActionType.OUTBOUND_MESSAGE in action_types
    # Persisted OUTBOUND_MESSAGE payload reflects the ORIGINAL content.
    out = next(r for r in rows if r.action_type == ActionType.OUTBOUND_MESSAGE)
    assert out.payload["content"] == "hello x"
    # POLICY_DECISION carries the pre/post-rewrite evidence.
    pol = next(r for r in rows if r.action_type == ActionType.POLICY_DECISION)
    assert pol.payload["target_action_id"] == out.action_id
    assert pol.payload["original_content"] == "hello x"
    assert pol.payload["post_content"] == "hello y"


@pytest.mark.asyncio
async def test_enforce_puts_rewritten_content_in_inbox(tmp_path: Path) -> None:
    """ENFORCE: inbox carries the REWRITTEN content; OUTBOUND_MESSAGE row matches."""

    session = _enforce_session(tmp_path, [RewriteMessageHook()])
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/send",
            json={"sender_id": "alice", "recipient_id": "bob", "content": "hello xxx"},
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["blocked"] is False

        recv = await client.post("/recv", json={"recipient_id": "bob"})
        assert recv.status == 200
        assert (await recv.json()) == {"sender_id": "alice", "content": "hello yyy"}

    rows = session.action_log.read_all()  # type: ignore[union-attr]
    out = next(r for r in rows if r.action_type == ActionType.OUTBOUND_MESSAGE)
    assert out.payload["content"] == "hello yyy"


@pytest.mark.asyncio
async def test_baseline_ignores_hooks_entirely(tmp_path: Path) -> None:
    """BASELINE: no hooks run even if the caller tries to attach them.

    ``Session.build`` drops any hooks under BASELINE since the condition
    is defined as "no audit infrastructure". We verify that property here
    AND that a hand-constructed Session with hooks still skips dispatch
    because the per-action gate short-circuits.
    """

    # Via Session.build: hooks must be dropped.
    session = Session.build(
        scenario_id="a5-baseline-hooks",
        condition=AuditCondition.BASELINE,
        db_path="/dev/null",
        hooks=[RewriteMessageHook()],
    )
    assert session.hooks == []

    # Hand-constructed session with hooks under BASELINE.
    hand = Session(
        scenario_id="hand-baseline",
        condition=AuditCondition.BASELINE,
        hooks=[RewriteMessageHook()],
    )
    outcome = await hand.record_outbound(
        sender_id="a", recipient_id="b", content="hello x"
    )
    assert outcome.action_id is None
    assert outcome.rewritten_content is None
    assert outcome.blocked is False
    # action_log stays None — no POLICY_DECISION was written anywhere.
    assert hand.action_log is None


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


@pytest.mark.asyncio
async def test_enforce_block_suppresses_inbox_and_returns_blocked_true(
    tmp_path: Path,
) -> None:
    """ENFORCE + block verdict: no inbox enqueue, no OUTBOUND_MESSAGE row."""

    class BlockOnWord:
        hook_kind = "message"

        def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
            if "BLOCKME" in action.payload.get("content", ""):
                return PolicyDecision(verdict=PolicyVerdict.BLOCK, policy_id="bl")
            return PolicyDecision(verdict=PolicyVerdict.ALLOW)

    session = _enforce_session(tmp_path, [BlockOnWord()])
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/send",
            json={"sender_id": "alice", "recipient_id": "bob", "content": "BLOCKME"},
        )
        assert resp.status == 200
        body = await resp.json()
        assert body == {"action_id": None, "blocked": True}

        # Inbox must be empty for bob.
        recv = await client.post("/recv", json={"recipient_id": "bob"})
        assert recv.status == 204

    rows = session.action_log.read_all()  # type: ignore[union-attr]
    types = [r.action_type for r in rows]
    assert ActionType.POLICY_DECISION in types
    assert ActionType.OUTBOUND_MESSAGE not in types


@pytest.mark.asyncio
async def test_enforce_tool_block_skips_mcp_dispatch(tmp_path: Path) -> None:
    """ENFORCE + tool-kind block: MCP dispatch is skipped, response carries blocked=true."""

    session = _enforce_session(tmp_path, [BlockToolHook()])
    # Register a tool so that without the block it would succeed.
    session.mcp_host.register("danger_tool", lambda **_: {"ok": True})
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/mcp/danger_tool",
            json={"agent_id": "alice", "arguments": {"x": 1}},
        )
        assert resp.status == 200
        body = await resp.json()
        assert body == {
            "tool_call_action_id": None,
            "tool_observation_action_id": None,
            "observation": None,
            "blocked": True,
        }

    rows = session.action_log.read_all()  # type: ignore[union-attr]
    types = [r.action_type for r in rows]
    # POLICY_DECISION captures the block; no TOOL_CALL or observation row.
    assert ActionType.POLICY_DECISION in types
    assert ActionType.TOOL_CALL not in types
    assert ActionType.TOOL_OBSERVATION_RETURN not in types


@pytest.mark.asyncio
async def test_mcp_dispatch_does_not_hold_audit_lock_during_tool_execution(
    tmp_path: Path,
) -> None:
    session = _enforce_session(tmp_path, [])

    def inspect_lock(_: dict) -> dict:
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


@pytest.mark.asyncio
async def test_enforce_memory_rewrite_replaces_persisted_content(tmp_path: Path) -> None:
    """ENFORCE + memory-kind rewrite: the persisted MEMORY_WRITE carries the rewrite."""

    session = _enforce_session(tmp_path, [RewriteMemoryHook()])
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/memory_write",
            json={"agent_id": "alice", "content": "the secret is 42"},
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["blocked"] is False

    rows = session.action_log.read_all()  # type: ignore[union-attr]
    mem = next(r for r in rows if r.action_type == ActionType.MEMORY_WRITE)
    assert mem.payload["content"] == "the [redacted] is 42"
    pol = next(r for r in rows if r.action_type == ActionType.POLICY_DECISION)
    assert pol.payload["target_action_id"] == mem.action_id


@pytest.mark.asyncio
async def test_shadow_log_mirrors_primary_on_passive_send(tmp_path: Path) -> None:
    """Every primary log append is mirrored to the shadow log under PASSIVE."""

    session = _passive_session(tmp_path, [RewriteMessageHook()])
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/send",
            json={"sender_id": "alice", "recipient_id": "bob", "content": "hello x"},
        )
        assert resp.status == 200

    primary = session.action_log.read_all()  # type: ignore[union-attr]
    shadow = session.shadow_log.read_all()  # type: ignore[union-attr]
    # Same number of rows, same action_ids in the same order, same
    # action_type sequence. prev_hash will legitimately differ because
    # each log has its own hash chain.
    assert len(primary) == len(shadow)
    assert [r.action_id for r in primary] == [r.action_id for r in shadow]
    assert [r.action_type for r in primary] == [r.action_type for r in shadow]


class MswmAwareRedactHook:
    """Rewrite hook that drops ``forbidden_item`` from mentioned_items.

    Mimics the MswmAwareHook rewrite mode: on trigger, returns a
    PolicyDecision whose ``rewritten_mentioned_items`` excludes the
    forbidden item. Used by the Fix-1 acceptance test to pin the MSWM
    reconciliation invariant.
    """

    hook_kind = "message"

    def __init__(self, forbidden_item: str) -> None:
        self._forbidden = forbidden_item

    def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
        mentioned = list(action.payload.get("mentioned_items") or [])
        if self._forbidden not in mentioned:
            return PolicyDecision(verdict=PolicyVerdict.ALLOW)
        rewritten = [m for m in mentioned if m != self._forbidden]
        return PolicyDecision(
            verdict=PolicyVerdict.REWRITE,
            rewritten_content=action.payload.get("content", "")
            + f" [redacted {self._forbidden}]",
            rewritten_mentioned_items=rewritten,
            policy_id="mswm-redact",
            reason=f"redact {self._forbidden}",
        )


@pytest.mark.asyncio
async def test_enforce_rewrite_updates_mswm_to_match_rewritten_content(
    tmp_path: Path,
) -> None:
    """ENFORCE + rewrite that drops a mentioned item ⇒ MSWM reflects the
    rewritten payload, not the original.

    This is the Codex-flagged Fix-1 invariant: previously the initial
    candidate action left tentative MSWM carrying the redacted item even
    though the persisted action removed it. Session now rebuilds
    transaction-local state from committed MSWM plus the rewritten candidate
    action so the peer's peer model agrees with the persisted payload.
    """

    session = _enforce_session(
        tmp_path, [MswmAwareRedactHook("forbidden_item")]
    )
    outcome = await session.record_outbound(
        sender_id="alice",
        recipient_id="bob",
        content="hello",
        mentioned_items=["ok_item", "forbidden_item"],
    )
    assert outcome.blocked is False
    assert outcome.rewritten_content is not None

    # MSWM must NOT carry forbidden_item on either side.
    sender_model = session.mswm.get("alice", "bob")
    recipient_model = session.mswm.get("bob", "alice")
    told_items = {item for item, _ in sender_model.items_told_to_j}
    learned_items = {item for item, _ in recipient_model.items_learned_from_j}
    assert told_items == {"ok_item"}
    assert learned_items == {"ok_item"}
    assert "forbidden_item" not in told_items
    assert "forbidden_item" not in learned_items


@pytest.mark.asyncio
async def test_passive_rewrite_leaves_mswm_reflecting_original(
    tmp_path: Path,
) -> None:
    """PASSIVE + rewrite verdict ⇒ MSWM still reflects the ORIGINAL payload.

    PASSIVE logs the rewrite as a policy_decision but the original
    action proceeds unchanged. MSWM, like the persisted record, mirrors
    the original (still-leaked) items_learned_from_j.
    """

    session = _passive_session(
        tmp_path, [MswmAwareRedactHook("forbidden_item")]
    )
    await session.record_outbound(
        sender_id="alice",
        recipient_id="bob",
        content="hello",
        mentioned_items=["ok_item", "forbidden_item"],
    )

    recipient_model = session.mswm.get("bob", "alice")
    learned_items = {item for item, _ in recipient_model.items_learned_from_j}
    # Under PASSIVE the original payload stands — forbidden_item leaked.
    assert learned_items == {"ok_item", "forbidden_item"}


@pytest.mark.asyncio
async def test_policy_decision_payload_carries_block_context(
    tmp_path: Path,
) -> None:
    """Blocked outbounds record recipient / mentioned_items / sources on the
    policy_decision row — there is no OUTBOUND_MESSAGE row to read from.
    """

    class BlockOnForbidden:
        hook_kind = "message"

        def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
            mentioned = action.payload.get("mentioned_items") or []
            if "forbidden_item" in mentioned:
                return PolicyDecision(
                    verdict=PolicyVerdict.BLOCK,
                    policy_id="bl",
                    reason="forbidden",
                )
            return PolicyDecision(verdict=PolicyVerdict.ALLOW)

    session = _enforce_session(tmp_path, [BlockOnForbidden()])
    outcome = await session.record_outbound(
        sender_id="alice",
        recipient_id="bob",
        content="hello",
        mentioned_items=["ok_item", "forbidden_item"],
        source_action_ids=["src-1", "src-2"],
    )
    assert outcome.blocked is True

    rows = session.action_log.read_all()  # type: ignore[union-attr]
    pol = next(r for r in rows if r.action_type == ActionType.POLICY_DECISION)
    assert pol.payload["verdict"] == "block"
    assert pol.payload["recipient_id"] == "bob"
    assert pol.payload["mentioned_items"] == ["ok_item", "forbidden_item"]
    assert pol.payload["source_action_ids"] == ["src-1", "src-2"]
    # Block does not carry a rewrite; field is explicit None.
    assert pol.payload["rewritten_mentioned_items"] is None


@pytest.mark.asyncio
async def test_policy_decision_payload_carries_rewrite_context(
    tmp_path: Path,
) -> None:
    """Rewrite verdicts record the rewritten_mentioned_items list."""

    session = _enforce_session(
        tmp_path, [MswmAwareRedactHook("forbidden_item")]
    )
    await session.record_outbound(
        sender_id="alice",
        recipient_id="bob",
        content="hello",
        mentioned_items=["ok_item", "forbidden_item"],
        source_action_ids=["src-1"],
    )

    rows = session.action_log.read_all()  # type: ignore[union-attr]
    pol = next(r for r in rows if r.action_type == ActionType.POLICY_DECISION)
    assert pol.payload["verdict"] == "rewrite"
    assert pol.payload["recipient_id"] == "bob"
    assert pol.payload["mentioned_items"] == ["ok_item", "forbidden_item"]
    assert pol.payload["rewritten_mentioned_items"] == ["ok_item"]
    assert pol.payload["source_action_ids"] == ["src-1"]
