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
