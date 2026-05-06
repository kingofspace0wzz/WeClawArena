from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from pydantic import BaseModel

from clawsocialarena.llm.costing import TokenUsage


@dataclass(frozen=True)
class OpenAIConfig:
    construction_model: str = "gpt-5"
    agent_model: str = "gpt-4.1-mini"


class OpenAIJsonResult(BaseModel):
    data: dict[str, Any]
    usage: TokenUsage


class JsonClient(Protocol):
    def create_json(
        self,
        *,
        model: str,
        system_prompt: str,
        payload: dict[str, Any],
        schema: dict[str, Any] | None = None,
        cache_key: str | None = None,
    ) -> OpenAIJsonResult:
        ...


OpenAIFactory = Callable[..., Any]


class OpenAIResponsesJsonClient:
    """Responses API wrapper isolated behind a mockable JSON interface."""

    def __init__(
        self,
        *,
        openai_factory: OpenAIFactory | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._openai_factory = openai_factory
        self._timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else _openai_request_timeout_seconds()
        )

    def create_json(
        self,
        *,
        model: str,
        system_prompt: str,
        payload: dict[str, Any],
        schema: dict[str, Any] | None = None,
        cache_key: str | None = None,
    ) -> OpenAIJsonResult:
        factory = self._openai_factory
        if factory is None:
            from openai import OpenAI

            factory = OpenAI

        client = factory(
            api_key=require_openai_key(),
            timeout=self._timeout_seconds,
        )
        kwargs: dict[str, Any] = {
            "model": model,
            "instructions": system_prompt,
            "input": json.dumps(payload, sort_keys=True),
            "store": False,
        }
        if schema is not None:
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "naturalization_patch",
                    "schema": schema,
                    "strict": False,
                }
            }
        else:
            kwargs["text"] = {"format": {"type": "json_object"}}
        if cache_key is not None:
            kwargs["prompt_cache_key"] = cache_key

        response = client.responses.create(**kwargs)
        return OpenAIJsonResult(
            data=_loads_response_json_object(_response_output_text(response)),
            usage=TokenUsage(
                model=model,
                input_tokens=_response_input_tokens(response),
                cached_input_tokens=_response_cached_tokens(response),
                output_tokens=_response_output_tokens(response),
            ),
        )


class OpenAIChatJsonClient:
    """Small OpenAI wrapper isolated behind a mockable JSON interface."""

    def __init__(self, *, timeout_seconds: float | None = None) -> None:
        self._timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else _openai_request_timeout_seconds()
        )

    def create_json(
        self,
        *,
        model: str,
        system_prompt: str,
        payload: dict[str, Any],
        schema: dict[str, Any] | None = None,
        cache_key: str | None = None,
    ) -> OpenAIJsonResult:
        from openai import OpenAI

        client = OpenAI(
            api_key=require_openai_key(),
            timeout=self._timeout_seconds,
        )
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(payload, sort_keys=True),
                },
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        usage = response.usage
        return OpenAIJsonResult(
            data=json.loads(content),
            usage=TokenUsage(
                model=model,
                input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                cached_input_tokens=_cached_tokens(usage),
                output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            ),
        )


def require_openai_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for paid LLM batch runs")
    return key


def _openai_request_timeout_seconds() -> float:
    raw = os.environ.get("OPENAI_REQUEST_TIMEOUT_SECONDS")
    if not raw:
        return 300.0
    try:
        value = float(raw)
    except ValueError:
        return 300.0
    return max(value, 30.0)


def _cached_tokens(usage: Any) -> int:
    details = getattr(usage, "prompt_tokens_details", None)
    if details is None:
        return 0
    if isinstance(details, dict):
        return int(details.get("cached_tokens") or 0)
    return int(getattr(details, "cached_tokens", 0) or 0)


def _response_output_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)
    fragments: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                fragments.append(str(text))
    return "".join(fragments) or "{}"


def _loads_response_json_object(text: str) -> dict[str, Any]:
    stripped = _strip_json_fence(text.strip())
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        data, _end = json.JSONDecoder().raw_decode(stripped)
    if not isinstance(data, dict):
        raise TypeError("OpenAI JSON response must decode to an object")
    return data


def _strip_json_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _response_usage(response: Any) -> Any:
    return getattr(response, "usage", None)


def _response_input_tokens(response: Any) -> int:
    usage = _response_usage(response)
    return int(getattr(usage, "input_tokens", 0) or 0)


def _response_cached_tokens(response: Any) -> int:
    usage = _response_usage(response)
    details = getattr(usage, "input_tokens_details", None)
    if isinstance(details, dict):
        return int(details.get("cached_tokens") or 0)
    return int(getattr(details, "cached_tokens", 0) or 0)


def _response_output_tokens(response: Any) -> int:
    usage = _response_usage(response)
    return int(getattr(usage, "output_tokens", 0) or 0)
