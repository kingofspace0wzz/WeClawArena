"""Tests for the in-gateway MCP host (Task A6).

The gateway hosts MCP tool servers in-process via :class:`McpHost`. Tool
handlers are registered by name and invoked through a single
``POST /mcp/{tool_name}`` route. Every dispatch records a pair of
``TOOL_CALL`` + ``TOOL_OBSERVATION_RETURN`` actions on the session's
action log (PASSIVE or ENFORCE) and returns the handler's observation
dict. Under BASELINE the handler still runs, but nothing is logged.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from clawsocialarena.gateway.mcp_host import McpHost
from clawsocialarena.gateway.server import build_app
from clawsocialarena.gateway.session import Session
from clawsocialarena.mcp_tools import noop
from clawsocialarena.types import ActionType, AuditCondition


def _make_passive_session(tmp_path: Path, suffix: str = "passive") -> Session:
    return Session.build(
        scenario_id=f"a6-{suffix}",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / f"a6-{suffix}.db",
    )


def _make_baseline_session() -> Session:
    return Session.build(
        scenario_id="a6-baseline",
        condition=AuditCondition.BASELINE,
        db_path="/dev/null",
    )


@pytest.mark.asyncio
async def test_mcp_noop_tool_logs_both_actions(tmp_path: Path) -> None:
    """PASSIVE: /mcp/noop dispatches and records both TOOL_CALL + TOOL_OBSERVATION_RETURN."""
    session = _make_passive_session(tmp_path, "noop")
    session.mcp_host.register("noop", noop)
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/mcp/noop",
            json={"agent_id": "alice", "arguments": {"foo": "bar"}},
        )
        assert resp.status == 200
        body = await resp.json()

    assert isinstance(body["tool_call_action_id"], str)
    assert body["tool_call_action_id"] != ""
    assert isinstance(body["tool_observation_action_id"], str)
    assert body["tool_observation_action_id"] != ""
    assert body["observation"] == {
        "ok": True,
        "echo": {"_agent_id": "alice", "foo": "bar"},
    }

    assert session.action_log is not None
    records = session.action_log.read_all()
    assert len(records) == 2

    call_rec, obs_rec = records
    assert call_rec.action_type == ActionType.TOOL_CALL
    assert call_rec.agent_id == "alice"
    assert call_rec.payload == {
        "tool_name": "noop",
        "arguments": {"foo": "bar"},
    }
    assert call_rec.action_id == body["tool_call_action_id"]

    assert obs_rec.action_type == ActionType.TOOL_OBSERVATION_RETURN
    assert obs_rec.agent_id == "alice"
    assert obs_rec.payload["tool_name"] == "noop"
    assert obs_rec.payload["tool_call_action_id"] == call_rec.action_id
    # Observation is serialized to JSON string for audit storage.
    import json
    assert json.loads(obs_rec.payload["observation"]) == {
        "ok": True,
        "echo": {"_agent_id": "alice", "foo": "bar"},
    }
    assert obs_rec.action_id == body["tool_observation_action_id"]


@pytest.mark.asyncio
async def test_mcp_unknown_tool_returns_404(tmp_path: Path) -> None:
    """Unregistered tool names yield HTTP 404; the attempted TOOL_CALL is still logged.

    The gateway records the ``TOOL_CALL`` before dispatch so the audit
    trail captures the attempt even when the handler is missing. No
    paired ``TOOL_OBSERVATION_RETURN`` is written in that case.
    """
    session = _make_passive_session(tmp_path, "unknown")
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/mcp/does_not_exist",
            json={"agent_id": "alice", "arguments": {}},
        )
        assert resp.status == 404
        body = await resp.json()
        assert body["error"] == "unknown tool"
        assert body["tool_name"] == "does_not_exist"

    assert session.action_log is not None
    records = session.action_log.read_all()
    assert len(records) == 1
    assert records[0].action_type == ActionType.TOOL_CALL
    assert records[0].payload["tool_name"] == "does_not_exist"


@pytest.mark.asyncio
async def test_mcp_validates_required_fields(tmp_path: Path) -> None:
    """Missing agent_id or arguments yields HTTP 400; invalid arguments type also 400."""
    session = _make_passive_session(tmp_path, "validate")
    session.mcp_host.register("noop", noop)
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        # Missing agent_id
        resp = await client.post("/mcp/noop", json={"arguments": {"foo": 1}})
        assert resp.status == 400

        # Missing arguments
        resp = await client.post("/mcp/noop", json={"agent_id": "alice"})
        assert resp.status == 400

        # arguments not a dict
        resp = await client.post(
            "/mcp/noop",
            json={"agent_id": "alice", "arguments": "not-a-dict"},
        )
        assert resp.status == 400


@pytest.mark.asyncio
async def test_mcp_dispatch_overwrites_spoofed_hidden_agent_id(
    tmp_path: Path,
) -> None:
    session = _make_passive_session(tmp_path, "hidden-agent")
    seen: list[dict] = []

    def inspect_args(arguments: dict) -> dict:
        seen.append(dict(arguments))
        return {"ok": True, "agent_id": arguments.get("_agent_id")}

    session.mcp_host.register("inspect_args", inspect_args)
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/mcp/inspect_args",
            json={
                "agent_id": "alice",
                "arguments": {"_agent_id": "bob", "x": 1},
            },
        )
        assert resp.status == 200
        body = await resp.json()

    assert body["observation"] == {"ok": True, "agent_id": "alice"}
    assert seen == [{"_agent_id": "alice", "x": 1}]


@pytest.mark.asyncio
async def test_mcp_host_register_and_dispatch_unit() -> None:
    """Unit test: McpHost directly registers handlers and dispatches to them."""
    host = McpHost()

    async def async_tool(arguments: dict) -> dict:
        return {"ok": True, "args": arguments}

    def sync_tool(arguments: dict) -> dict:
        return {"ok": True, "sync": True, "args": arguments}

    host.register("async_tool", async_tool)
    host.register("sync_tool", sync_tool)

    assert set(host.tools()) == {"async_tool", "sync_tool"}

    result_async = await host.dispatch("async_tool", {"x": 1})
    assert result_async == {"ok": True, "args": {"x": 1}}

    result_sync = await host.dispatch("sync_tool", {"y": 2})
    assert result_sync == {"ok": True, "sync": True, "args": {"y": 2}}

    with pytest.raises(KeyError):
        await host.dispatch("missing", {})

    # Re-registering overwrites the prior handler.
    async def replacement(arguments: dict) -> dict:
        return {"replaced": True}

    host.register("async_tool", replacement)
    result_replaced = await host.dispatch("async_tool", {})
    assert result_replaced == {"replaced": True}


@pytest.mark.asyncio
async def test_mcp_handler_exception_logs_call_without_observation(tmp_path: Path) -> None:
    """Non-KeyError exceptions from a handler propagate as HTTP 500.

    The gateway records the ``TOOL_CALL`` before dispatching, then calls
    the handler. When the handler raises something other than ``KeyError``
    (which the route translates to 404 for "unknown tool"), the exception
    bubbles up to aiohttp, which responds with HTTP 500. The audit log
    must keep exactly one record for the attempt: the pre-dispatch
    ``TOOL_CALL``. No orphan ``TOOL_OBSERVATION_RETURN`` is written,
    since the observation never materialized.
    """
    session = _make_passive_session(tmp_path, "handler-exc")

    async def boom(_arguments: dict) -> dict:
        raise ValueError("boom")

    session.mcp_host.register("boom", boom)
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/mcp/boom",
            json={"agent_id": "alice", "arguments": {"x": 1}},
        )
        assert resp.status == 500

    assert session.action_log is not None
    records = session.action_log.read_all()
    assert len(records) == 1
    assert records[0].action_type == ActionType.TOOL_CALL
    assert records[0].payload == {"tool_name": "boom", "arguments": {"x": 1}}


@pytest.mark.asyncio
async def test_mcp_noop_under_baseline_runs_but_does_not_log() -> None:
    """BASELINE: the noop tool still runs and returns observation; no log entries."""
    session = _make_baseline_session()
    session.mcp_host.register("noop", noop)
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/mcp/noop",
            json={"agent_id": "alice", "arguments": {"hello": "world"}},
        )
        assert resp.status == 200
        body = await resp.json()

    assert body["observation"] == {
        "ok": True,
        "echo": {"_agent_id": "alice", "hello": "world"},
    }
    assert body["tool_call_action_id"] is None
    assert body["tool_observation_action_id"] is None
    assert session.action_log is None
