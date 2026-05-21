"""Unit tests for the Bedrock JsonClient and the provider dispatcher.

The Bedrock client is exercised with a fake boto3 ``bedrock-runtime``
client injected via ``bedrock_factory`` so the tests do not touch AWS.
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest

from clawsocialarena.llm.bedrock_client import (
    BedrockJsonClient,
    _convert_tool_schema,
)
from clawsocialarena.llm.openai_client import (
    ProviderDispatchClient,
    is_bedrock_model,
)


class _FakeBody:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._buf = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def read(self) -> bytes:
        return self._buf.read()


class _FakeBedrockRuntime:
    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def invoke_model(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"body": _FakeBody(self._response)}


# ---------------------------------------------------------------------------
# Dispatcher routing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model_id",
    [
        "anthropic.claude-sonnet-4-6",
        "global.anthropic.claude-opus-4-7",
        "us.anthropic.claude-sonnet-4-5-v2:0",
        "eu.anthropic.claude-3-5-sonnet-20240620-v1:0",
        "APAC.Anthropic.Claude-3-Haiku",  # case-insensitive
    ],
)
def test_is_bedrock_model_recognizes_anthropic_prefixes(model_id: str) -> None:
    assert is_bedrock_model(model_id)


@pytest.mark.parametrize(
    "model_id",
    ["gpt-4.1-mini", "gpt-5.2", "claude-sonnet-without-prefix", ""],
)
def test_is_bedrock_model_rejects_other_ids(model_id: str) -> None:
    assert not is_bedrock_model(model_id)


def test_dispatcher_routes_bedrock_models_to_bedrock_client() -> None:
    class _Stub:
        def __init__(self) -> None:
            self.create_json_calls: list[str] = []
            self.create_with_tools_calls: list[str] = []

        def create_json(self, *, model: str, **_: Any) -> Any:
            self.create_json_calls.append(model)
            return "bedrock-json"

        def create_with_tools(self, *, model: str, **_: Any) -> Any:
            self.create_with_tools_calls.append(model)
            return "bedrock-tools"

    bedrock = _Stub()
    openai = _Stub()
    dispatcher = ProviderDispatchClient(
        openai_client=openai, bedrock_client=bedrock
    )

    dispatcher.create_json(
        model="anthropic.claude-sonnet-4-6",
        system_prompt="hi",
        payload={"x": 1},
    )
    dispatcher.create_with_tools(
        model="global.anthropic.claude-opus-4-7",
        system_prompt="hi",
        payload={"x": 1},
        tools=[],
    )
    dispatcher.create_json(
        model="gpt-4.1-mini", system_prompt="hi", payload={"y": 2}
    )
    dispatcher.create_with_tools(
        model="gpt-5.2",
        system_prompt="hi",
        payload={"y": 2},
        tools=[],
    )

    assert bedrock.create_json_calls == ["anthropic.claude-sonnet-4-6"]
    assert bedrock.create_with_tools_calls == ["global.anthropic.claude-opus-4-7"]
    assert openai.create_json_calls == ["gpt-4.1-mini"]
    assert openai.create_with_tools_calls == ["gpt-5.2"]


# ---------------------------------------------------------------------------
# Bedrock create_json
# ---------------------------------------------------------------------------


def test_bedrock_create_json_returns_decoded_object_and_usage() -> None:
    fake = _FakeBedrockRuntime(
        {
            "content": [
                {"type": "text", "text": '{"answer": 42}'},
            ],
            "usage": {
                "input_tokens": 123,
                "output_tokens": 17,
                "cache_read_input_tokens": 9,
            },
        }
    )
    client = BedrockJsonClient(bedrock_factory=lambda **_: fake)

    result = client.create_json(
        model="anthropic.claude-sonnet-4-6",
        system_prompt="Return JSON.",
        payload={"q": "hello"},
        schema={"type": "object", "properties": {"answer": {"type": "integer"}}},
    )

    assert result.data == {"answer": 42}
    assert result.usage.input_tokens == 123
    assert result.usage.output_tokens == 17
    assert result.usage.cached_input_tokens == 9
    assert result.usage.model == "anthropic.claude-sonnet-4-6"

    assert len(fake.calls) == 1
    sent = json.loads(fake.calls[0]["body"])
    assert sent["anthropic_version"] == "bedrock-2023-05-31"
    assert sent["messages"][0]["role"] == "user"
    assert "JSON Schema" in sent["system"]
    assert fake.calls[0]["modelId"] == "anthropic.claude-sonnet-4-6"


def test_bedrock_create_json_strips_code_fence() -> None:
    fake = _FakeBedrockRuntime(
        {
            "content": [
                {"type": "text", "text": "```json\n{\"ok\": true}\n```"},
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    )
    client = BedrockJsonClient(bedrock_factory=lambda **_: fake)

    result = client.create_json(
        model="anthropic.claude-sonnet-4-6",
        system_prompt="x",
        payload={},
    )
    assert result.data == {"ok": True}


# ---------------------------------------------------------------------------
# Bedrock create_with_tools
# ---------------------------------------------------------------------------


def test_bedrock_create_with_tools_emits_tool_call() -> None:
    fake = _FakeBedrockRuntime(
        {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_abc",
                    "name": "finalize_proposal",
                    "input": {"price": 12, "quantity": 3},
                }
            ],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
    )
    client = BedrockJsonClient(bedrock_factory=lambda **_: fake)

    tools = [
        {
            "type": "function",
            "name": "finalize_proposal",
            "description": "Send a final price + quantity proposal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "price": {"type": "number"},
                    "quantity": {"type": "integer"},
                },
                "required": ["price", "quantity"],
            },
        }
    ]

    result = client.create_with_tools(
        model="anthropic.claude-sonnet-4-6",
        system_prompt="Negotiate.",
        payload={"turn": 1},
        tools=tools,
    )

    assert result.content == ""
    assert len(result.tool_calls) == 1
    call = result.tool_calls[0]
    assert call.call_id == "toolu_abc"
    assert call.name == "finalize_proposal"
    assert call.arguments == {"price": 12, "quantity": 3}
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 5

    sent = json.loads(fake.calls[0]["body"])
    assert sent["tools"][0]["name"] == "finalize_proposal"
    assert "input_schema" in sent["tools"][0]
    assert "parameters" not in sent["tools"][0]


def test_bedrock_create_with_tools_emits_text_content_when_no_tool_use() -> None:
    fake = _FakeBedrockRuntime(
        {
            "content": [{"type": "text", "text": "  hello there  "}],
            "usage": {"input_tokens": 1, "output_tokens": 2},
        }
    )
    client = BedrockJsonClient(bedrock_factory=lambda **_: fake)

    result = client.create_with_tools(
        model="anthropic.claude-sonnet-4-6",
        system_prompt="x",
        payload={"x": 1},
        tools=[],
    )

    assert result.tool_calls == []
    assert result.content == "hello there"


def test_convert_tool_schema_drops_function_type_and_renames_parameters() -> None:
    schema = {
        "type": "function",
        "name": "x",
        "description": "y",
        "parameters": {"type": "object", "properties": {"a": {"type": "string"}}},
    }
    out = _convert_tool_schema(schema)
    assert out == {
        "name": "x",
        "description": "y",
        "input_schema": {"type": "object", "properties": {"a": {"type": "string"}}},
    }
