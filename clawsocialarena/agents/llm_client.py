"""LLMClient protocol and provider implementations.

Providers:
- MockLLMClient (canned completions for tests)
- BedrockLLMClient (Anthropic Messages API via boto3)
- OpenAILLMClient (OpenAI SDK)

DeepSeek and Qwen providers follow the OpenAI-compatible pattern and can be
added in Phase 5 when needed. See spec §5.3.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: str
    content: str


class LLMCompletion(BaseModel):
    content: str
    tool_calls: list[dict] | None = None
    usage: dict[str, int] | None = None


@runtime_checkable
class LLMClient(Protocol):
    def complete(
        self,
        *,
        messages: list[LLMMessage],
        tools: list[dict] | None,
        params: dict[str, Any],
    ) -> LLMCompletion: ...


class MockLLMClient:
    """Canned-response client for deterministic tests.

    Each canned response may be:
    - a ``str``: returned as ``LLMCompletion(content=..., tool_calls=None)``; or
    - a ``dict`` with optional ``content`` / ``tool_calls`` keys: passed through
      to ``LLMCompletion`` so tests can simulate tool-using completions.
    """

    def __init__(self, canned_responses: list[str | dict]) -> None:
        if not canned_responses:
            raise ValueError("MockLLMClient requires at least one canned response")
        self._responses: list[str | dict] = list(canned_responses)
        self._i = 0

    def complete(
        self,
        *,
        messages: list[LLMMessage],
        tools: list[dict] | None,
        params: dict[str, Any],
    ) -> LLMCompletion:
        item = self._responses[self._i % len(self._responses)]
        self._i += 1
        if isinstance(item, str):
            return LLMCompletion(content=item, tool_calls=None, usage={"mock": 1})
        return LLMCompletion(
            content=item.get("content", ""),
            tool_calls=item.get("tool_calls"),
            usage=item.get("usage", {"mock": 1}),
        )


class BedrockLLMClient:
    """Anthropic Messages API via AWS Bedrock Runtime.

    Expects credentials from the standard boto3 chain (env / profile / IRSA).
    Model IDs are full Bedrock ARNs, e.g. ``anthropic.claude-sonnet-4-6-v1:0``.
    """

    def __init__(self, *, model_id: str, region: str = "us-west-2") -> None:
        import boto3  # imported lazily so tests don't require AWS

        self._model_id = model_id
        self._client = boto3.client("bedrock-runtime", region_name=region)

    def complete(
        self,
        *,
        messages: list[LLMMessage],
        tools: list[dict] | None,
        params: dict[str, Any],
    ) -> LLMCompletion:
        import json

        body: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": [
                {"role": m.role, "content": [{"type": "text", "text": m.content}]}
                for m in messages
                if m.role != "system"
            ],
            "max_tokens": int(params.get("max_tokens", 2048)),
            "temperature": float(params.get("temperature", 0.2)),
        }
        system_msg = next((m for m in messages if m.role == "system"), None)
        if system_msg is not None:
            body["system"] = [
                {
                    "type": "text",
                    "text": system_msg.content,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        if tools:
            body["tools"] = tools
        resp = self._client.invoke_model(
            modelId=self._model_id, body=json.dumps(body).encode("utf-8")
        )
        payload = json.loads(resp["body"].read())
        text_blocks = [b for b in payload.get("content", []) if b.get("type") == "text"]
        content = "".join(b["text"] for b in text_blocks)
        tool_calls = [b for b in payload.get("content", []) if b.get("type") == "tool_use"]
        return LLMCompletion(
            content=content,
            tool_calls=tool_calls or None,
            usage=payload.get("usage"),
        )


class OpenAILLMClient:
    def __init__(self, *, model_id: str) -> None:
        from openai import OpenAI

        self._model_id = model_id
        self._client = OpenAI()

    def complete(
        self,
        *,
        messages: list[LLMMessage],
        tools: list[dict] | None,
        params: dict[str, Any],
    ) -> LLMCompletion:
        resp = self._client.chat.completions.create(
            model=self._model_id,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            tools=tools if tools else None,
            temperature=float(params.get("temperature", 0.2)),
            max_tokens=int(params.get("max_tokens", 2048)),
        )
        choice = resp.choices[0]
        content = choice.message.content or ""
        tool_calls = choice.message.tool_calls or None
        return LLMCompletion(
            content=content,
            tool_calls=[tc.model_dump() for tc in tool_calls] if tool_calls else None,
            usage=resp.usage.model_dump() if resp.usage else None,
        )
