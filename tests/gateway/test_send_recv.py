"""Tests for the gateway ``/send`` and ``/recv`` endpoints (Task A3).

These cover the minimal inbox roundtrip wired on the Session: a PASSIVE
session logs an ``outbound_message`` ActionRecord and enqueues the message;
a matching ``/recv`` pops it. BASELINE short-circuits the log append and
returns a null ``action_id``. Missing fields produce HTTP 400.

Policy hooks, phase tagging, shadow double-write, and cassette recording
all arrive in later tasks; this file asserts only the plumbing implemented
in A3.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from clawsocialarena.gateway.server import build_app
from clawsocialarena.gateway.session import Session
from clawsocialarena.types import AuditCondition


def _make_passive_session(tmp_path: Path) -> Session:
    return Session.build(
        scenario_id="a3-passive",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "a3-passive.db",
    )


def _make_baseline_session() -> Session:
    return Session.build(
        scenario_id="a3-baseline",
        condition=AuditCondition.BASELINE,
        db_path="/dev/null",
    )


@pytest.mark.asyncio
async def test_send_recv_roundtrip(tmp_path: Path) -> None:
    """Passive session: /send logs an outbound_message and enqueues; /recv pops it."""
    session = _make_passive_session(tmp_path)
    app = build_app(session)
    assert isinstance(app, web.Application)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/send",
            json={"sender_id": "alice", "recipient_id": "bob", "content": "hello"},
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["action_id"] is not None
        assert isinstance(body["action_id"], str)

        resp2 = await client.post("/recv", json={"recipient_id": "bob"})
        assert resp2.status == 200
        body2 = await resp2.json()
        assert body2 == {"sender_id": "alice", "content": "hello"}

        resp3 = await client.post("/recv", json={"recipient_id": "bob"})
        assert resp3.status == 204

    # Sanity check: the outbound_message record actually landed in the ActionLog.
    assert session.action_log is not None
    records = session.action_log.read_all()
    assert len(records) == 1
    rec = records[0]
    assert rec.agent_id == "alice"
    assert rec.action_type.value == "outbound_message"
    assert rec.payload == {"recipient_id": "bob", "content": "hello"}


@pytest.mark.asyncio
async def test_send_under_baseline_returns_null_action_id() -> None:
    """BASELINE: /send still enqueues for delivery but returns action_id=null."""
    session = _make_baseline_session()
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/send",
            json={"sender_id": "alice", "recipient_id": "bob", "content": "hi"},
        )
        assert resp.status == 200
        body = await resp.json()
        assert body == {"action_id": None, "blocked": False}

        # The message should still be deliverable: baseline is audit-free but
        # the gateway still routes traffic.
        resp2 = await client.post("/recv", json={"recipient_id": "bob"})
        assert resp2.status == 200
        assert await resp2.json() == {"sender_id": "alice", "content": "hi"}

    assert session.action_log is None


@pytest.mark.asyncio
async def test_send_validates_required_fields(tmp_path: Path) -> None:
    """/send returns HTTP 400 when sender_id, recipient_id, or content is missing."""
    session = _make_passive_session(tmp_path)
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        missing_cases = [
            {"recipient_id": "bob", "content": "hi"},
            {"sender_id": "alice", "content": "hi"},
            {"sender_id": "alice", "recipient_id": "bob"},
            {},
        ]
        for payload in missing_cases:
            resp = await client.post("/send", json=payload)
            assert resp.status == 400, f"expected 400 for payload {payload}"


@pytest.mark.asyncio
async def test_recv_empty_inbox_returns_204(tmp_path: Path) -> None:
    """/recv on an unknown recipient returns 204 and does not crash."""
    session = _make_passive_session(tmp_path)
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/recv", json={"recipient_id": "nobody"})
        assert resp.status == 204


@pytest.mark.asyncio
async def test_recv_validates_required_recipient(tmp_path: Path) -> None:
    """/recv returns HTTP 400 when recipient_id is missing."""
    session = _make_passive_session(tmp_path)
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/recv", json={})
        assert resp.status == 400


@pytest.mark.asyncio
async def test_send_threads_source_action_ids_into_record(tmp_path: Path) -> None:
    """Optional source_action_ids on /send lands in ActionRecord.source_action_ids.

    Phase A.5 Fix 3: MSWM (C) and attribution (F) walk this list to
    derive causal links without positional heuristics, so the gateway
    must persist whatever the caller provides verbatim.
    """

    session = _make_passive_session(tmp_path)
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/send",
            json={
                "sender_id": "alice",
                "recipient_id": "bob",
                "content": "hi",
                "source_action_ids": ["act-upstream-1", "act-upstream-2"],
            },
        )
        assert resp.status == 200

    assert session.action_log is not None
    rows = session.action_log.read_all()
    assert len(rows) == 1
    assert rows[0].source_action_ids == ["act-upstream-1", "act-upstream-2"]


@pytest.mark.asyncio
async def test_send_rejects_malformed_source_action_ids(tmp_path: Path) -> None:
    """Non-array source_action_ids yields a uniform HTTP 400."""

    session = _make_passive_session(tmp_path)
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/send",
            json={
                "sender_id": "alice",
                "recipient_id": "bob",
                "content": "hi",
                "source_action_ids": "not-an-array",
            },
        )
        assert resp.status == 400
        body = await resp.json()
        assert body["field"] == "source_action_ids"


@pytest.mark.asyncio
async def test_memory_write_threads_source_action_ids(tmp_path: Path) -> None:
    """/memory_write forwards source_action_ids into the ActionRecord."""

    session = _make_passive_session(tmp_path)
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/memory_write",
            json={
                "agent_id": "alice",
                "content": "note",
                "tags": ["t1"],
                "source_action_ids": ["act-source"],
            },
        )
        assert resp.status == 200

    rows = session.action_log.read_all()  # type: ignore[union-attr]
    assert len(rows) == 1
    assert rows[0].source_action_ids == ["act-source"]
