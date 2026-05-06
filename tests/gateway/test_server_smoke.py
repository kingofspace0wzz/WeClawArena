"""Smoke tests for the gateway HTTP scaffold (Task A1)."""

from __future__ import annotations

import argparse
import json
import socket

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from clawsocialarena.gateway.server import _build_default_session, build_app
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


def test_default_session_accepts_work_dir_for_cassette(tmp_path):
    session = _build_default_session(
        argparse.Namespace(
            scenario_id="smoke",
            condition=AuditCondition.PASSIVE.value,
            db_path=str(tmp_path / "action_log.db"),
            work_dir=str(tmp_path),
            gt_path=None,
            resource_root=None,
        )
    )

    try:
        assert session.condition == AuditCondition.PASSIVE
        assert session.action_log is not None
        assert session.shadow_log is not None
        assert session.cassette is not None
        assert (tmp_path / "cassette.jsonl").exists()
    finally:
        session.close()


def test_default_session_loads_phase_schedule_from_gt_path(tmp_path):
    gt_path = tmp_path / "scenario.gt.json"
    gt_path.write_text(
        json.dumps(
            {
                "scenario_id": "smoke",
                "terminal_predicate": {"type": "none"},
                "phase_schedule": [
                    {"phase": "discovery", "start_turn": 0, "end_turn": 2},
                    {"phase": "negotiation", "start_turn": 2, "end_turn": 5},
                ],
            }
        ),
        encoding="utf-8",
    )

    session = _build_default_session(
        argparse.Namespace(
            scenario_id="smoke",
            condition=AuditCondition.PASSIVE.value,
            db_path=str(tmp_path / "action_log.db"),
            work_dir=str(tmp_path),
            gt_path=str(gt_path),
            resource_root=None,
        )
    )

    try:
        assert session.phase_tracker is not None
        session.phase_tracker.advance_to_turn(2)
        assert session.phase_tracker.current_phase().value == "negotiation"
    finally:
        session.close()
