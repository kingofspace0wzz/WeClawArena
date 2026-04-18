"""Tests for the gateway side-channel endpoints (Task A4).

Task A4 adds four endpoints that let out-of-process agents report events
that happen outside the message bus: tool invocations, tool observations,
memory writes, and LLM call accounting. Each endpoint drops the event
into the session's ``ActionLog`` under the appropriate ``action_type``
with a payload that matches the v1 ``AuditedMessageBus`` schemas (and, for
``llm_call``, the token-accounting schema defined in the A4 task brief).

The tests below assert only the plumbing landed in A4: the append goes
into ``session.action_log`` with the right type and payload keys, BASELINE
short-circuits with a null ``action_id``, and missing fields yield 400.
Policy hooks, phase tagging, shadow double-write, and cassette recording
all arrive in later tasks.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from clawsocialarena.gateway.server import build_app
from clawsocialarena.gateway.session import Session
from clawsocialarena.types import AuditCondition


def _make_passive_session(tmp_path: Path, suffix: str = "passive") -> Session:
    return Session.build(
        scenario_id=f"a4-{suffix}",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / f"a4-{suffix}.db",
    )


def _make_baseline_session() -> Session:
    return Session.build(
        scenario_id="a4-baseline",
        condition=AuditCondition.BASELINE,
        db_path="/dev/null",
    )


@pytest.mark.asyncio
async def test_tool_call_logs_action(tmp_path: Path) -> None:
    """Passive session: /tool_call appends a TOOL_CALL record with tool_name + arguments."""
    session = _make_passive_session(tmp_path, "toolcall")
    app = build_app(session)

    payload = {
        "agent_id": "alice",
        "tool_name": "web_search",
        "arguments": {"query": "audit logs", "top_k": 3},
    }

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/tool_call", json=payload)
        assert resp.status == 200
        body = await resp.json()
        assert isinstance(body["action_id"], str)
        assert body["action_id"] != ""

    assert session.action_log is not None
    records = session.action_log.read_all()
    assert len(records) == 1
    rec = records[0]
    assert rec.agent_id == "alice"
    assert rec.action_type.value == "tool_call"
    assert rec.payload == {
        "tool_name": "web_search",
        "arguments": {"query": "audit logs", "top_k": 3},
    }
    assert rec.action_id == body["action_id"]


@pytest.mark.asyncio
async def test_tool_observation_return_logs_action(tmp_path: Path) -> None:
    """Passive session: /tool_observation_return appends a linked TOOL_OBSERVATION_RETURN."""
    session = _make_passive_session(tmp_path, "toolobs")
    app = build_app(session)

    payload = {
        "agent_id": "alice",
        "tool_call_action_id": "tc-deadbeef0001",
        "tool_name": "web_search",
        "observation": "3 results returned",
    }

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/tool_observation_return", json=payload)
        assert resp.status == 200
        body = await resp.json()
        assert isinstance(body["action_id"], str)

    assert session.action_log is not None
    records = session.action_log.read_all()
    assert len(records) == 1
    rec = records[0]
    assert rec.agent_id == "alice"
    assert rec.action_type.value == "tool_observation_return"
    assert rec.payload == {
        "tool_call_action_id": "tc-deadbeef0001",
        "tool_name": "web_search",
        "observation": "3 results returned",
    }


@pytest.mark.asyncio
async def test_memory_write_logs_action(tmp_path: Path) -> None:
    """Passive session: /memory_write appends MEMORY_WRITE; tags default to [] when omitted."""
    session = _make_passive_session(tmp_path, "memw")
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/memory_write",
            json={"agent_id": "alice", "content": "bob prefers async comms"},
        )
        assert resp.status == 200
        body = await resp.json()
        assert isinstance(body["action_id"], str)

        resp2 = await client.post(
            "/memory_write",
            json={
                "agent_id": "alice",
                "content": "bob lives in Berlin",
                "tags": ["location", "bio"],
            },
        )
        assert resp2.status == 200

    assert session.action_log is not None
    records = session.action_log.read_all()
    assert len(records) == 2

    first = records[0]
    assert first.agent_id == "alice"
    assert first.action_type.value == "memory_write"
    assert first.payload == {"content": "bob prefers async comms", "tags": []}

    second = records[1]
    assert second.action_type.value == "memory_write"
    assert second.payload == {
        "content": "bob lives in Berlin",
        "tags": ["location", "bio"],
    }


@pytest.mark.asyncio
async def test_llm_call_logs_action(tmp_path: Path) -> None:
    """Passive session: /llm_call appends an LLM_CALL with the six token/latency/model fields."""
    session = _make_passive_session(tmp_path, "llm")
    app = build_app(session)

    payload = {
        "agent_id": "alice",
        "input_tokens": 1024,
        "output_tokens": 256,
        "cached_tokens": 512,
        "latency_ms": 734,
        "model": "claude-4-7-opus",
    }

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/llm_call", json=payload)
        assert resp.status == 200
        body = await resp.json()
        assert isinstance(body["action_id"], str)

    assert session.action_log is not None
    records = session.action_log.read_all()
    assert len(records) == 1
    rec = records[0]
    assert rec.agent_id == "alice"
    assert rec.action_type.value == "llm_call"
    assert rec.payload == {
        "input_tokens": 1024,
        "output_tokens": 256,
        "cached_tokens": 512,
        "latency_ms": 734,
        "model": "claude-4-7-opus",
    }


@pytest.mark.asyncio
async def test_llm_call_defaults_cached_tokens_to_zero(tmp_path: Path) -> None:
    """/llm_call omits cached_tokens and the server defaults it to 0 in the payload."""
    session = _make_passive_session(tmp_path, "llmdef")
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/llm_call",
            json={
                "agent_id": "alice",
                "input_tokens": 10,
                "output_tokens": 5,
                "latency_ms": 100,
                "model": "claude-4-7-opus",
            },
        )
        assert resp.status == 200

    records = session.action_log.read_all()
    assert len(records) == 1
    assert records[0].payload["cached_tokens"] == 0


@pytest.mark.asyncio
async def test_side_channel_validates_required_fields(tmp_path: Path) -> None:
    """/tool_call returns HTTP 400 when any of agent_id/tool_name/arguments is absent."""
    session = _make_passive_session(tmp_path, "tc400")
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        # Missing tool_name
        resp = await client.post(
            "/tool_call",
            json={"agent_id": "alice", "arguments": {"q": "hi"}},
        )
        assert resp.status == 400

        # Missing agent_id
        resp = await client.post(
            "/tool_call",
            json={"tool_name": "web_search", "arguments": {"q": "hi"}},
        )
        assert resp.status == 400

        # Missing arguments
        resp = await client.post(
            "/tool_call",
            json={"agent_id": "alice", "tool_name": "web_search"},
        )
        assert resp.status == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path, payload",
    [
        (
            "/tool_call",
            {"agent_id": "alice", "tool_name": "web_search", "arguments": {"q": "hi"}},
        ),
        (
            "/tool_observation_return",
            {
                "agent_id": "alice",
                "tool_call_action_id": "tc-abc",
                "tool_name": "web_search",
                "observation": "ok",
            },
        ),
        (
            "/memory_write",
            {"agent_id": "alice", "content": "note"},
        ),
        (
            "/llm_call",
            {
                "agent_id": "alice",
                "input_tokens": 1,
                "output_tokens": 1,
                "latency_ms": 1,
                "model": "claude-4-7-opus",
            },
        ),
    ],
)
async def test_side_channels_under_baseline_return_null_action_id(
    path: str, payload: dict
) -> None:
    """BASELINE: each side-channel endpoint returns action_id=null with no log append."""
    session = _make_baseline_session()
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(path, json=payload)
        assert resp.status == 200
        body = await resp.json()
        assert body.get("action_id") is None
        # /tool_call and /memory_write responses carry blocked=False under
        # baseline because a future ENFORCE hook could set it to True; the
        # schema is uniform across conditions so clients do not branch.
        if path in ("/tool_call", "/memory_write"):
            assert body.get("blocked") is False

    assert session.action_log is None
