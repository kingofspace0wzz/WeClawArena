"""HTTP route handlers for the gateway.

Task A1 introduced :func:`healthz`. Task A3 adds :func:`send` and
:func:`recv`, which together form the minimal message-exchange surface
the out-of-process agents use to talk through the gateway. Task A4 adds
four side-channel endpoints, :func:`tool_call`,
:func:`tool_observation_return`, :func:`memory_write`, and
:func:`llm_call`, which let agents report events that bypass the message
bus (tool invocations, tool observations, memory writes, and LLM token
accounting). Phase A.5 ports the enforce/passive policy-hook semantics
into the :class:`Session`; each route now awaits a
:class:`~clawsocialarena.gateway.session.RecordOutcome` and, for ``/send``
and ``/mcp/{tool_name}``, reflects ``block`` / ``rewrite`` verdicts back
to the caller: blocked sends return ``{"blocked": true}`` and are never
enqueued on the recipient inbox; rewritten sends go out with the
rewritten content; blocked tool calls skip the MCP dispatch.

Every route that records an action also accepts an optional
``source_action_ids`` array which is threaded through to the ActionRecord
so Phase C (MSWM) and Phase F (attribution) can walk the provenance
chain without positional heuristics.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiohttp import web
from pydantic import ValidationError

from clawsocialarena.gateway.session import Session
from clawsocialarena.types import GovernanceRecord


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


def _parse_source_action_ids(body: dict) -> list[str] | web.Response:
    """Return the optional ``source_action_ids`` array or a 400 response.

    Accepts an absent key (default ``[]``), an explicit ``null`` (also
    coerced to ``[]``), or a list of strings. Any other shape produces a
    uniform HTTP 400 so the caller can surface the error identically to
    the other ``invalid_field_type`` responses in this module.
    """

    raw: Any = body.get("source_action_ids")
    if raw is None:
        return []
    if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        return list(raw)
    return web.json_response(
        {
            "error": "invalid_field_type",
            "field": "source_action_ids",
            "expected": "array[str]",
        },
        status=400,
    )


def _parse_turn_index(body: dict) -> int | None | web.Response:
    """Return optional non-negative ``turn_index`` or a uniform 400 response."""

    raw: Any = body.get("turn_index")
    if raw is None:
        return None
    if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
        return raw
    return web.json_response(
        {
            "error": "invalid_field_type",
            "field": "turn_index",
            "expected": "non-negative integer",
        },
        status=400,
    )


def _parse_governance(body: dict) -> GovernanceRecord | None | web.Response:
    """Return optional governance context or a uniform 400 response."""

    raw: Any = body.get("governance")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return web.json_response(
            {
                "error": "invalid_field_type",
                "field": "governance",
                "expected": "object",
            },
            status=400,
        )
    try:
        return GovernanceRecord.model_validate(raw)
    except ValidationError as exc:
        return web.json_response(
            {
                "error": "invalid_field_type",
                "field": "governance",
                "expected": "GovernanceRecord",
                "details": exc.errors(),
            },
            status=400,
        )


async def send(request: web.Request) -> web.Response:
    """Enqueue a message for ``recipient_id`` and log an outbound record.

    Request JSON: ``{"sender_id": str, "recipient_id": str, "content": str,
    "source_action_ids": list[str]?, "mentioned_items": list[str]?,
    "enqueue": bool?}``. Response JSON:
    ``{"action_id": str | null, "blocked": bool}`` with HTTP 200.

    Under BASELINE the ``action_id`` is ``null`` and the message is still
    enqueued so recipients can ``/recv`` it, mirroring the "deployment
    without audit infrastructure" condition in spec §5.1. Under PASSIVE
    the message is enqueued unchanged and every hook verdict is logged as
    a POLICY_DECISION. Under ENFORCE a ``rewrite`` verdict replaces the
    enqueued content; a ``block`` verdict suppresses the enqueue entirely
    and the response carries ``"blocked": true``.

    Missing any of the three required fields yields HTTP 400, as does an
    invalid ``source_action_ids`` payload.
    """

    body = await _read_json(request)
    missing = _require_fields(body, "sender_id", "recipient_id", "content")
    if missing:
        return _bad_request(missing)

    sender_id: str = body["sender_id"]
    recipient_id: str = body["recipient_id"]
    content: str = body["content"]

    sources = _parse_source_action_ids(body)
    if isinstance(sources, web.Response):
        return sources
    governance = _parse_governance(body)
    if isinstance(governance, web.Response):
        return governance
    turn_index = _parse_turn_index(body)
    if isinstance(turn_index, web.Response):
        return turn_index
    declared_action_id_raw: Any = body.get("declared_action_id")
    declared_action_id: str | None = None
    if "declared_action_id" in body:
        if not isinstance(declared_action_id_raw, str) or not declared_action_id_raw:
            return web.json_response(
                {
                    "error": "invalid_field_type",
                    "field": "declared_action_id",
                    "expected": "non-empty string",
                },
                status=400,
            )
        declared_action_id = declared_action_id_raw

    # Phase C: optional ``mentioned_items`` list drives MSWM disclosure
    # updates. Accept absent / null / array-of-string; anything else is a
    # 400. Preserve an explicitly empty list as audited "checked no item"
    # evidence; absence remains None and omits the payload key.
    raw_mentioned: Any = body.get("mentioned_items")
    mentioned: list[str] | None = None
    if "mentioned_items" in body and raw_mentioned is not None:
        if not isinstance(raw_mentioned, list) or not all(
            isinstance(x, str) for x in raw_mentioned
        ):
            return web.json_response(
                {
                    "error": "invalid_field_type",
                    "field": "mentioned_items",
                    "expected": "array[str]",
                },
                status=400,
            )
        mentioned = list(raw_mentioned)
    elif "mentioned_items" in body:
        mentioned = []

    enqueue_raw = body.get("enqueue", True)
    if not isinstance(enqueue_raw, bool):
        return web.json_response(
            {"error": "invalid_field_type", "field": "enqueue", "expected": "bool"},
            status=400,
        )

    session = _get_session(request)
    if enqueue_raw:
        outcome = await session.send_outbound(
            sender_id=sender_id,
            recipient_id=recipient_id,
            content=content,
            source_action_ids=sources,
            mentioned_items=mentioned,
            declared_action_id=declared_action_id,
            governance=governance,
            turn_index=turn_index,
        )
    else:
        outcome = await session.record_outbound(
            sender_id=sender_id,
            recipient_id=recipient_id,
            content=content,
            source_action_ids=sources,
            mentioned_items=mentioned,
            declared_action_id=declared_action_id,
            governance=governance,
            turn_index=turn_index,
        )
    if outcome.blocked:
        # ENFORCE block: no inbox enqueue, caller gets a structured hint.
        return web.json_response({"action_id": None, "blocked": True})

    return web.json_response({"action_id": outcome.action_id, "blocked": False})


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
        ``{"agent_id": str, "tool_name": str, "arguments": dict,
           "source_action_ids": list[str]?}``.

    Response JSON: ``{"action_id": str | null, "blocked": bool}``. Missing
    required fields yield HTTP 400. Under BASELINE the log append is
    skipped and the response carries ``action_id=null`` with ``blocked=false``;
    the endpoint still returns 200 so the calling agent does not have to
    branch on the condition. Under ENFORCE a hook-driven block sets
    ``blocked=true`` and suppresses the log row.
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

    sources = _parse_source_action_ids(body)
    if isinstance(sources, web.Response):
        return sources
    governance = _parse_governance(body)
    if isinstance(governance, web.Response):
        return governance
    turn_index = _parse_turn_index(body)
    if isinstance(turn_index, web.Response):
        return turn_index

    session = _get_session(request)
    outcome = await session.record_tool_call(
        agent_id=body["agent_id"],
        tool_name=body["tool_name"],
        arguments=arguments,
        source_action_ids=sources,
        governance=governance,
        turn_index=turn_index,
    )
    return web.json_response(
        {"action_id": outcome.action_id, "blocked": outcome.blocked}
    )


async def tool_observation_return(request: web.Request) -> web.Response:
    """Log a ``TOOL_OBSERVATION_RETURN`` linked to a prior tool call.

    Request JSON: ``{"agent_id": str, "tool_call_action_id": str,
    "tool_name": str, "observation": str, "source_action_ids": list[str]?}``.
    Missing required fields yield HTTP 400. Baseline short-circuits with a
    null ``action_id``.
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

    sources = _parse_source_action_ids(body)
    if isinstance(sources, web.Response):
        return sources
    governance = _parse_governance(body)
    if isinstance(governance, web.Response):
        return governance
    turn_index = _parse_turn_index(body)
    if isinstance(turn_index, web.Response):
        return turn_index

    session = _get_session(request)
    outcome = await session.record_tool_observation(
        agent_id=body["agent_id"],
        tool_call_action_id=body["tool_call_action_id"],
        tool_name=body["tool_name"],
        observation=body["observation"],
        source_action_ids=sources,
        governance=governance,
        turn_index=turn_index,
    )
    return web.json_response(
        {"action_id": outcome.action_id, "blocked": outcome.blocked}
    )


async def memory_write(request: web.Request) -> web.Response:
    """Log a ``MEMORY_WRITE`` action record.

    Request JSON: ``{"agent_id": str, "content": str, "tags": list[str],
    "source_action_ids": list[str]?}``. ``tags`` is optional and defaults
    to the empty list in the resulting payload. Missing ``agent_id`` or
    ``content`` yields HTTP 400. Baseline short-circuits with a null
    ``action_id``. Under ENFORCE a ``block`` verdict returns
    ``blocked=true`` without persisting the memory write.
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

    sources = _parse_source_action_ids(body)
    if isinstance(sources, web.Response):
        return sources
    governance = _parse_governance(body)
    if isinstance(governance, web.Response):
        return governance
    turn_index = _parse_turn_index(body)
    if isinstance(turn_index, web.Response):
        return turn_index

    session = _get_session(request)
    outcome = await session.record_memory_write(
        agent_id=body["agent_id"],
        content=body["content"],
        tags=tags,
        source_action_ids=sources,
        governance=governance,
        turn_index=turn_index,
    )
    return web.json_response(
        {"action_id": outcome.action_id, "blocked": outcome.blocked}
    )


async def mcp_dispatch(request: web.Request) -> web.Response:
    """Dispatch a tool call to the session's in-process ``McpHost``.

    Path: ``POST /mcp/{tool_name}``.
    Request JSON:
        ``{"agent_id": str, "arguments": dict,
           "source_action_ids": list[str]?}``.
    Response JSON:
        ``{"tool_call_action_id": str | null,
           "tool_observation_action_id": str | null,
           "observation": dict,
           "blocked": bool}``.

    Flow: validate the two required fields, record a ``TOOL_CALL`` action,
    dispatch through ``session.mcp_host``, record a
    ``TOOL_OBSERVATION_RETURN`` linked to the call, and return the
    observation dict unchanged. Unknown tool names yield HTTP 404;
    missing or malformed fields yield HTTP 400. Under BASELINE both
    action ids are ``null`` but the handler still runs. Under ENFORCE a
    hook-driven ``block`` on the TOOL_CALL short-circuits the dispatch:
    no MCP call, no observation row, and the response carries
    ``"blocked": true`` with both action ids ``null``.
    """

    tool_name = request.match_info["tool_name"]
    body = await _read_json(request)
    missing = _require_fields(body, "agent_id", "arguments")
    if missing:
        return _bad_request(missing)

    arguments = body["arguments"]
    if not isinstance(arguments, dict):
        return web.json_response(
            {"error": "invalid_field_type", "field": "arguments", "expected": "object"},
            status=400,
        )

    sources = _parse_source_action_ids(body)
    if isinstance(sources, web.Response):
        return sources
    governance = _parse_governance(body)
    if isinstance(governance, web.Response):
        return governance
    turn_index = _parse_turn_index(body)
    if isinstance(turn_index, web.Response):
        return turn_index

    agent_id: str = body["agent_id"]
    session = _get_session(request)

    tc_outcome = await session.record_tool_call(
        agent_id=agent_id,
        tool_name=tool_name,
        arguments=arguments,
        source_action_ids=sources,
        governance=governance,
        turn_index=turn_index,
    )
    if tc_outcome.blocked:
        return web.json_response(
            {
                "tool_call_action_id": None,
                "tool_observation_action_id": None,
                "observation": None,
                "blocked": True,
            }
        )

    handler_arguments = dict(arguments)
    handler_arguments["_agent_id"] = agent_id
    try:
        observation = await session.mcp_host.dispatch(tool_name, handler_arguments)
    except KeyError:
        return web.json_response(
            {"error": "unknown tool", "tool_name": tool_name},
            status=404,
        )

    obs_outcome = await session.record_tool_observation(
        agent_id=agent_id,
        tool_call_action_id=tc_outcome.action_id,
        tool_name=tool_name,
        observation=json.dumps(observation, sort_keys=True, ensure_ascii=False),
        source_action_ids=sources,
        governance=governance,
        turn_index=turn_index,
    )
    if obs_outcome.blocked:
        return web.json_response(
            {
                "tool_call_action_id": tc_outcome.action_id,
                "tool_observation_action_id": None,
                "observation": None,
                "blocked": True,
            }
        )

    return web.json_response(
        {
            "tool_call_action_id": tc_outcome.action_id,
            "tool_observation_action_id": obs_outcome.action_id,
            "observation": observation,
            "blocked": False,
        }
    )


async def llm_call(request: web.Request) -> web.Response:
    """Log an ``LLM_CALL`` token-accounting record.

    Request JSON: ``{"agent_id": str, "input_tokens": int,
    "output_tokens": int, "cached_tokens": int, "latency_ms": int,
    "model": str, "source_action_ids": list[str]?}``. ``cached_tokens``
    is optional and defaults to 0. Baseline short-circuits with a null
    ``action_id``.
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

    sources = _parse_source_action_ids(body)
    if isinstance(sources, web.Response):
        return sources
    governance = _parse_governance(body)
    if isinstance(governance, web.Response):
        return governance
    turn_index = _parse_turn_index(body)
    if isinstance(turn_index, web.Response):
        return turn_index

    session = _get_session(request)
    outcome = await session.record_llm_call(
        agent_id=body["agent_id"],
        input_tokens=body["input_tokens"],
        output_tokens=body["output_tokens"],
        cached_tokens=cached_tokens,
        latency_ms=body["latency_ms"],
        model=body["model"],
        source_action_ids=sources,
        governance=governance,
        turn_index=turn_index,
    )
    return web.json_response(
        {"action_id": outcome.action_id, "blocked": outcome.blocked}
    )
