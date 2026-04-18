"""Docker-free smoke for the v2 gateway HTTP surface.

Usage:
    python -m scripts.run_mvp

What it does:
    1. Builds a BASELINE ``Session`` (``scenario_id='mvp'``) with the audit
       substrate disabled, because BASELINE is the simplest path through the
       gateway: /send still enqueues, /recv still pops, and no ActionLog has
       to be opened.
    2. Starts the gateway HTTP app inside an ``aiohttp.test_utils.TestServer``
       (in-process, no subprocess, no Docker).
    3. Posts a scripted ``/send`` from "alice" to "bob".
    4. Pops it with ``/recv`` and prints the message body.
    5. Asserts the message matches, then exits 0.

Not in scope for this smoke:
    - Real compose orchestration. Phase G of the v2 refactor will land a
      separate ``scripts/run_grid.py`` that brings up OpenClaw containers
      via ``docker compose`` and drives them through ``ComposeRunner``.
    - LLM calls. Scripted sends skip the ``/llm_call`` endpoint so no
      provider keys are required.
    - Policy hooks, MSWM, phase tagging. Those live under PASSIVE / ENFORCE
      and are covered by the Phase A pytest suite.

This script exists primarily for human inspection. The automated coverage
for the same code paths lives in ``tests/gateway/test_send_recv.py`` and
``tests/gateway/test_server_smoke.py``.
"""

from __future__ import annotations

import asyncio

from aiohttp.test_utils import TestClient, TestServer

from clawsocialarena.gateway.server import build_app
from clawsocialarena.gateway.session import Session
from clawsocialarena.types import AuditCondition


async def main() -> None:
    session = Session.build(
        scenario_id="mvp",
        condition=AuditCondition.BASELINE,
        db_path="/dev/null",
    )
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        send_resp = await client.post(
            "/send",
            json={
                "sender_id": "alice",
                "recipient_id": "bob",
                "content": "hello from run_mvp",
            },
        )
        assert send_resp.status == 200, f"/send returned {send_resp.status}"
        send_body = await send_resp.json()
        print(f"/send -> status={send_resp.status} body={send_body}")

        recv_resp = await client.post("/recv", json={"recipient_id": "bob"})
        assert recv_resp.status == 200, f"/recv returned {recv_resp.status}"
        recv_body = await recv_resp.json()
        print(f"/recv -> status={recv_resp.status} body={recv_body}")

        assert recv_body == {
            "sender_id": "alice",
            "content": "hello from run_mvp",
        }, f"unexpected /recv body: {recv_body}"

    print("run_mvp: OK")


if __name__ == "__main__":
    asyncio.run(main())
