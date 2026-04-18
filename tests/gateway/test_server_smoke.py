"""Smoke tests for the gateway HTTP scaffold (Task A1)."""

from __future__ import annotations

import socket

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from clawsocialarena.gateway.server import build_app
from clawsocialarena.gateway.session import Session
from clawsocialarena.types import AuditCondition


def _free_port() -> int:
    """Return an OS-assigned free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.asyncio
async def test_server_health():
    """GET /healthz on a live aiohttp server returns {"ok": true} on a free port."""
    session = Session.build(
        scenario_id="smoke",
        condition=AuditCondition.BASELINE,
        db_path="/dev/null",
    )
    app = build_app(session)
    assert isinstance(app, web.Application)

    port = _free_port()
    async with TestClient(TestServer(app, port=port)) as client:
        resp = await client.get("/healthz")
        assert resp.status == 200
        body = await resp.json()
        assert body == {"ok": True}
