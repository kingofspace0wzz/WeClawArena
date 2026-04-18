"""HTTP route handlers for the gateway.

Task A1 introduced :func:`healthz`. Task A3 adds :func:`send` and
:func:`recv`, which together form the minimal message-exchange surface
the out-of-process agents use to talk through the gateway. Policy-hook
evaluation, cassette recording, and shadow-log double-writes arrive in
later tasks; this module intentionally does only the action-log append
and inbox queue management.
"""

from __future__ import annotations

import asyncio
import json

from aiohttp import web

from clawsocialarena.gateway.session import Session


async def healthz(_request: web.Request) -> web.Response:
    """Liveness probe: returns ``{"ok": true}`` with HTTP 200."""
    return web.json_response({"ok": True})


async def _read_json(request: web.Request) -> dict:
    """Parse the request body as JSON, returning ``{}`` on empty or invalid."""
    if not request.body_exists:
        return {}
    try:
        data = await request.json()
    except (json.JSONDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _get_session(request: web.Request) -> Session:
    """Fetch the Session stashed on the aiohttp application by :func:`build_app`."""
    session = request.app.get("session")
    if session is None:
        raise RuntimeError("gateway app is missing a Session (build_app was bypassed)")
    return session


async def send(request: web.Request) -> web.Response:
    """Enqueue a message for ``recipient_id`` and log an outbound record.

    Request JSON: ``{"sender_id": str, "recipient_id": str, "content": str}``.
    Response JSON: ``{"action_id": str | null}`` with HTTP 200. Under
    BASELINE the ``action_id`` is ``null``; under PASSIVE or ENFORCE it is
    the freshly-minted ActionLog id.

    Note: under BASELINE the message is still enqueued so recipients can
    ``/recv`` it, even though no audit record is written; this mirrors the
    "deployment without audit infrastructure" condition in spec §5.1.

    Missing any of the three required fields yields HTTP 400.
    """

    body = await _read_json(request)
    sender_id = body.get("sender_id")
    recipient_id = body.get("recipient_id")
    content = body.get("content")

    missing = [
        name
        for name, value in (
            ("sender_id", sender_id),
            ("recipient_id", recipient_id),
            ("content", content),
        )
        if not isinstance(value, str) or value == ""
    ]
    if missing:
        return web.json_response(
            {"error": "missing_required_fields", "fields": missing},
            status=400,
        )

    session = _get_session(request)
    action_id = session.record_outbound(
        sender_id=sender_id,
        recipient_id=recipient_id,
        content=content,
    )
    inbox = session.ensure_inbox(recipient_id)
    await inbox.put((sender_id, content))
    return web.json_response({"action_id": action_id})


async def recv(request: web.Request) -> web.Response:
    """Pop the next message for ``recipient_id`` non-blocking, or return 204.

    Request JSON: ``{"recipient_id": str}``. When the inbox queue is empty
    or has not yet been materialized, the response is HTTP 204 No Content.
    Otherwise the response is ``{"sender_id": str, "content": str}`` with
    HTTP 200.
    """

    body = await _read_json(request)
    recipient_id = body.get("recipient_id")
    if not isinstance(recipient_id, str) or recipient_id == "":
        return web.json_response(
            {"error": "missing_required_fields", "fields": ["recipient_id"]},
            status=400,
        )

    session = _get_session(request)
    inbox = session.inboxes.get(recipient_id)
    if inbox is None:
        return web.Response(status=204)

    try:
        sender_id, content = inbox.get_nowait()
    except asyncio.QueueEmpty:
        return web.Response(status=204)

    return web.json_response({"sender_id": sender_id, "content": content})
