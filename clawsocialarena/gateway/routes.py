"""HTTP route handlers for the gateway.

Task A1 introduced :func:`healthz`. Task A3 adds :func:`send` and
:func:`recv`, which together form the minimal message-exchange surface
the out-of-process agents use to talk through the gateway. Task A4 adds
four side-channel endpoints, :func:`tool_call`,
:func:`tool_observation_return`, :func:`memory_write`, and
:func:`llm_call`, which let agents report events that bypass the message
bus (tool invocations, tool observations, memory writes, and LLM token
accounting). Policy-hook evaluation, cassette recording, and shadow-log
double-writes arrive in later tasks; this module intentionally does only
the action-log append and inbox queue management.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

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


def _require_fields(data: dict, *keys: str) -> list[str]:
    """Return the list of ``keys`` that are missing from ``data``.

    Presence means ``key in body and body[key] is not None``; empty dicts,
    empty strings, and empty lists are allowed (per-handler type checks
    enforce stricter semantics, e.g. the ``arguments`` dict on
    ``/tool_call`` or the integer fields on ``/llm_call``). The shape of
    the return value lets each handler turn a missing list into a uniform
    400 response:

        missing = _require_fields(body, "agent_id", "content")
        if missing:
            return _bad_request(missing)
    """
    missing: list[str] = []
    for key in keys:
        if key not in data or data[key] is None:
            missing.append(key)
    return missing


def _bad_request(missing: list[str]) -> web.Response:
    """Construct a uniform 400 response listing the missing fields."""
    return web.json_response(
        {"error": "missing_required_fields", "fields": missing},
        status=400,
    )


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
    missing = _require_fields(body, "sender_id", "recipient_id", "content")
    if missing:
        return _bad_request(missing)

    sender_id: str = body["sender_id"]
    recipient_id: str = body["recipient_id"]
    content: str = body["content"]

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
        return _bad_request(["recipient_id"])

    session = _get_session(request)
    inbox = session.inboxes.get(recipient_id)
    if inbox is None:
        return web.Response(status=204)

    try:
        sender_id, content = inbox.get_nowait()
    except asyncio.QueueEmpty:
        return web.Response(status=204)

    return web.json_response({"sender_id": sender_id, "content": content})


async def tool_call(request: web.Request) -> web.Response:
    """Log a ``TOOL_CALL`` action record reported by an agent.

    Request JSON:
        ``{"agent_id": str, "tool_name": str, "arguments": dict}``.

    Response JSON: ``{"action_id": str | null}``. Missing required fields
    yield HTTP 400. Under BASELINE the log append is skipped and the
    response carries ``action_id=null``; the endpoint still returns 200
    so the calling agent does not have to branch on the condition.
    """

    body = await _read_json(request)
    missing = _require_fields(body, "agent_id", "tool_name", "arguments")
    if missing:
        return _bad_request(missing)

    arguments = body["arguments"]
    if not isinstance(arguments, dict):
        return web.json_response(
            {"error": "invalid_field_type", "field": "arguments", "expected": "object"},
            status=400,
        )

    session = _get_session(request)
    action_id = session.record_tool_call(
        agent_id=body["agent_id"],
        tool_name=body["tool_name"],
        arguments=arguments,
    )
    return web.json_response({"action_id": action_id})


async def tool_observation_return(request: web.Request) -> web.Response:
    """Log a ``TOOL_OBSERVATION_RETURN`` linked to a prior tool call.

    Request JSON: ``{"agent_id": str, "tool_call_action_id": str,
    "tool_name": str, "observation": str}``. Missing required fields
    yield HTTP 400. Baseline short-circuits with a null ``action_id``.
    """

    body = await _read_json(request)
    missing = _require_fields(
        body,
        "agent_id",
        "tool_call_action_id",
        "tool_name",
        "observation",
    )
    if missing:
        return _bad_request(missing)

    session = _get_session(request)
    action_id = session.record_tool_observation(
        agent_id=body["agent_id"],
        tool_call_action_id=body["tool_call_action_id"],
        tool_name=body["tool_name"],
        observation=body["observation"],
    )
    return web.json_response({"action_id": action_id})


async def memory_write(request: web.Request) -> web.Response:
    """Log a ``MEMORY_WRITE`` action record.

    Request JSON: ``{"agent_id": str, "content": str, "tags": list[str]}``.
    ``tags`` is optional and defaults to the empty list in the resulting
    payload. Missing ``agent_id`` or ``content`` yields HTTP 400. Baseline
    short-circuits with a null ``action_id``.
    """

    body = await _read_json(request)
    missing = _require_fields(body, "agent_id", "content")
    if missing:
        return _bad_request(missing)

    raw_tags: Any = body.get("tags")
    if raw_tags is None:
        tags: list[str] = []
    elif isinstance(raw_tags, list) and all(isinstance(t, str) for t in raw_tags):
        tags = list(raw_tags)
    else:
        return web.json_response(
            {"error": "invalid_field_type", "field": "tags", "expected": "array[str]"},
            status=400,
        )

    session = _get_session(request)
    action_id = session.record_memory_write(
        agent_id=body["agent_id"],
        content=body["content"],
        tags=tags,
    )
    return web.json_response({"action_id": action_id})


async def llm_call(request: web.Request) -> web.Response:
    """Log an ``LLM_CALL`` token-accounting record.

    Request JSON: ``{"agent_id": str, "input_tokens": int,
    "output_tokens": int, "cached_tokens": int, "latency_ms": int,
    "model": str}``. ``cached_tokens`` is optional and defaults to 0.
    Baseline short-circuits with a null ``action_id``.
    """

    body = await _read_json(request)
    missing = _require_fields(
        body,
        "agent_id",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "model",
    )
    if missing:
        return _bad_request(missing)

    cached_tokens = body.get("cached_tokens", 0)
    if cached_tokens is None:
        cached_tokens = 0

    for name, value in (
        ("input_tokens", body["input_tokens"]),
        ("output_tokens", body["output_tokens"]),
        ("cached_tokens", cached_tokens),
        ("latency_ms", body["latency_ms"]),
    ):
        if not isinstance(value, int) or isinstance(value, bool):
            return web.json_response(
                {"error": "invalid_field_type", "field": name, "expected": "integer"},
                status=400,
            )

    session = _get_session(request)
    action_id = session.record_llm_call(
        agent_id=body["agent_id"],
        input_tokens=body["input_tokens"],
        output_tokens=body["output_tokens"],
        cached_tokens=cached_tokens,
        latency_ms=body["latency_ms"],
        model=body["model"],
    )
    return web.json_response({"action_id": action_id})
