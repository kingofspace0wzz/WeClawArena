"""Bedrock JsonClient for Anthropic Claude models.

Implements the same ``JsonClient`` protocol as
``OpenAIResponsesJsonClient`` (see ``openai_client.py``) so the agent
loop, naturalizer, and docker agent runner can dispatch Claude rows to
Bedrock's Anthropic Messages API via boto3 without any other code
changes. The dispatch decision lives in
:class:`clawsocialarena.llm.openai_client.ProviderDispatchClient`.

Tool-schema bridge: the agent loop hands schemas in the OpenAI
Responses-API shape (``{"type": "function", "name": ..., "parameters":
...}``). The Anthropic Messages API expects
``{"name": ..., "input_schema": ...}``. :func:`_convert_tool_schema`
maps between the two; the tool-call response is normalized into
``OpenAIToolCall`` records so downstream code keeps the same
representation regardless of provider.

Usage accounting: Anthropic returns ``usage.input_tokens`` /
``usage.output_tokens`` and (when prompt caching is hit)
``usage.cache_read_input_tokens``. We thread these through
``TokenUsage`` so cost reporting works unchanged.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

from clawsocialarena.llm.costing import TokenUsage
from clawsocialarena.llm.openai_client import (
    OpenAIJsonResult,
    OpenAIToolCall,
    OpenAIToolCallResult,
    _loads_response_json_object,
)

logger = logging.getLogger(__name__)


BedrockFactory = Callable[..., Any]


_DEFAULT_MAX_TOKENS = 4096
_DEFAULT_TIMEOUT_SECONDS = 300.0
_ANTHROPIC_VERSION = "bedrock-2023-05-31"


def _max_tokens_default() -> int:
    raw = os.environ.get("BEDROCK_MAX_TOKENS")
    if not raw:
        return _DEFAULT_MAX_TOKENS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_TOKENS
    return max(value, 1)


def _request_timeout_seconds() -> float:
    raw = os.environ.get("BEDROCK_REQUEST_TIMEOUT_SECONDS")
    if not raw:
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS
    return max(value, 30.0)


def _resolve_region() -> str:
    return (
        os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )


class BedrockJsonClient:
    """``JsonClient`` backed by AWS Bedrock's Anthropic Messages API.

    The boto3 client is created lazily on first use so import-time
    cost is zero and tests can inject a stub via ``bedrock_factory``.
    """

    def __init__(
        self,
        *,
        bedrock_factory: BedrockFactory | None = None,
        region: str | None = None,
        timeout_seconds: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self._bedrock_factory = bedrock_factory
        self._region = region or _resolve_region()
        self._timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else _request_timeout_seconds()
        )
        self._max_tokens = max_tokens if max_tokens is not None else _max_tokens_default()
        self._client: Any = None

    def _runtime(self) -> Any:
        if self._client is not None:
            return self._client
        factory = self._bedrock_factory
        if factory is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self._region,
                config=Config(
                    read_timeout=self._timeout_seconds,
                    connect_timeout=min(self._timeout_seconds, 30.0),
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
        else:
            self._client = factory(
                region_name=self._region,
                timeout_seconds=self._timeout_seconds,
            )
        return self._client

    def create_json(
        self,
        *,
        model: str,
        system_prompt: str,
        payload: dict[str, Any],
        schema: dict[str, Any] | None = None,
        cache_key: str | None = None,
    ) -> OpenAIJsonResult:
        del cache_key  # Anthropic prompt caching is opt-in via cache_control; not wired yet.
        system = system_prompt
        if schema is not None:
            system = (
                f"{system_prompt}\n\nRespond with a single JSON object that "
                "validates against this JSON Schema:\n"
                + json.dumps(schema, sort_keys=True)
            )
        else:
            system = (
                f"{system_prompt}\n\nRespond with a single JSON object and "
                "nothing else."
            )

        body = {
            "anthropic_version": _ANTHROPIC_VERSION,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(payload, sort_keys=True),
                }
            ],
        }
        decoded = self._invoke(model=model, body=body)
        text = _join_text_blocks(decoded.get("content") or [])
        usage = _token_usage_from_anthropic(model, decoded.get("usage") or {})
        try:
            data = _loads_response_json_object(text or "{}")
        except (ValueError, TypeError) as exc:
            _log_empty_response(
                "create_json",
                model=model,
                decoded=decoded,
                body=body,
                returned_text=text,
                parse_error=str(exc),
            )
            raise
        if not text.strip():
            _log_empty_response(
                "create_json", model=model, decoded=decoded, body=body,
                returned_text=text,
            )
        return OpenAIJsonResult(data=data, usage=usage)

    def create_with_tools(
        self,
        *,
        model: str,
        system_prompt: str,
        payload: dict[str, Any],
        tools: list[dict[str, Any]],
        cache_key: str | None = None,
    ) -> OpenAIToolCallResult:
        del cache_key
        body: dict[str, Any] = {
            "anthropic_version": _ANTHROPIC_VERSION,
            "max_tokens": self._max_tokens,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(payload, sort_keys=True),
                }
            ],
            "tools": [_convert_tool_schema(t) for t in tools],
        }
        decoded = self._invoke(model=model, body=body)
        tool_calls, content_text = _parse_anthropic_content(
            decoded.get("content") or []
        )
        if not tool_calls and not content_text.strip():
            _log_empty_response(
                "create_with_tools", model=model, decoded=decoded, body=body
            )
        return OpenAIToolCallResult(
            tool_calls=tool_calls,
            content=content_text.strip(),
            usage=_token_usage_from_anthropic(model, decoded.get("usage") or {}),
        )

    def _invoke(self, *, model: str, body: dict[str, Any]) -> dict[str, Any]:
        response = self._runtime().invoke_model(
            modelId=model,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        raw = response["body"].read() if hasattr(response["body"], "read") else response["body"]
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        return json.loads(raw or "{}")


def _convert_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Map an OpenAI Responses-API tool schema to the Anthropic shape.

    Input::

        {"type": "function", "name": "x", "description": "...",
         "parameters": {"type": "object", ...}}

    Output::

        {"name": "x", "description": "...",
         "input_schema": {"type": "object", ...}}
    """
    return {
        "name": str(schema.get("name") or ""),
        "description": str(schema.get("description") or ""),
        "input_schema": schema.get("parameters") or {"type": "object"},
    }


def _join_text_blocks(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "".join(parts)


def _parse_anthropic_content(
    blocks: list[dict[str, Any]],
) -> tuple[list[OpenAIToolCall], str]:
    tool_calls: list[OpenAIToolCall] = []
    text_parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "tool_use":
            raw_input = block.get("input") or {}
            arguments: dict[str, Any]
            if isinstance(raw_input, dict):
                arguments = raw_input
            elif isinstance(raw_input, str):
                try:
                    decoded = json.loads(raw_input) if raw_input else {}
                except (ValueError, TypeError):
                    decoded = {}
                arguments = decoded if isinstance(decoded, dict) else {}
            else:
                arguments = {}
            tool_calls.append(
                OpenAIToolCall(
                    call_id=str(block.get("id") or ""),
                    name=str(block.get("name") or ""),
                    arguments=arguments,
                )
            )
        elif block_type == "text":
            text_parts.append(str(block.get("text") or ""))
    return tool_calls, "".join(text_parts)


def _log_empty_response(
    call_kind: str,
    *,
    model: str,
    decoded: dict[str, Any],
    body: dict[str, Any],
    returned_text: str | None = None,
    parse_error: str | None = None,
) -> None:
    """Emit a structured warning when Bedrock returns no usable content.

    Captures stop_reason, the content-block type histogram, and request
    shape (system length, user content length, tool count, max_tokens) so
    failure modes can be diagnosed without re-running. Also writes a JSONL
    record to ``$BEDROCK_DEBUG_DIR`` (if set) for offline inspection.
    """
    content_blocks = decoded.get("content") or []
    block_types: dict[str, int] = {}
    sample_block: dict[str, Any] | None = None
    for b in content_blocks:
        t = (b.get("type") or "unknown") if isinstance(b, dict) else "non_dict"
        block_types[t] = block_types.get(t, 0) + 1
        if sample_block is None and isinstance(b, dict):
            sample_block = {k: b.get(k) for k in ("type", "text", "name") if k in b}

    system_field = body.get("system") or ""
    if isinstance(system_field, list):
        system_len = sum(
            len((part or {}).get("text", "")) if isinstance(part, dict) else 0
            for part in system_field
        )
    else:
        system_len = len(str(system_field))
    messages = body.get("messages") or []
    user_len = 0
    if messages and isinstance(messages[0], dict):
        c = messages[0].get("content")
        if isinstance(c, str):
            user_len = len(c)
        elif isinstance(c, list):
            user_len = sum(
                len((part or {}).get("text", "")) if isinstance(part, dict) else 0
                for part in c
            )

    record = {
        "kind": "bedrock_empty_response",
        "call": call_kind,
        "model": model,
        "stop_reason": decoded.get("stop_reason"),
        "stop_sequence": decoded.get("stop_sequence"),
        "block_types": block_types,
        "n_content_blocks": len(content_blocks),
        "sample_block": sample_block,
        "returned_text_preview": (
            (returned_text or "")[:500] if returned_text else None
        ),
        "returned_text_chars": len(returned_text) if returned_text is not None else None,
        "parse_error": parse_error,
        "usage": decoded.get("usage"),
        "request": {
            "system_chars": system_len,
            "user_chars": user_len,
            "n_tools": len(body.get("tools") or []),
            "max_tokens": body.get("max_tokens"),
            "anthropic_version": body.get("anthropic_version"),
        },
    }
    logger.warning("bedrock empty response: %s", json.dumps(record, sort_keys=True))

    debug_dir = os.environ.get("BEDROCK_DEBUG_DIR")
    if debug_dir:
        try:
            os.makedirs(debug_dir, exist_ok=True)
            path = os.path.join(debug_dir, "bedrock_empty_responses.jsonl")
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, sort_keys=True) + "\n")
        except OSError:
            pass


def _token_usage_from_anthropic(model: str, usage: dict[str, Any]) -> TokenUsage:
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    cached = int(usage.get("cache_read_input_tokens") or 0)
    return TokenUsage(
        model=model,
        input_tokens=input_tokens,
        cached_input_tokens=cached,
        output_tokens=output_tokens,
    )
