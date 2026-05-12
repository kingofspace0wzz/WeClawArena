import pytest
from types import SimpleNamespace

from clawsocialarena.llm.openai_client import (
    OpenAIConfig,
    OpenAIResponsesJsonClient,
    require_openai_key,
)


def test_require_openai_key_rejects_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        require_openai_key()


def test_openai_config_defaults_to_pinned_models() -> None:
    config = OpenAIConfig()

    assert config.construction_model == "gpt-5.2"
    assert config.agent_model == "gpt-4.1-mini"


def test_responses_json_client_extracts_json_and_usage(monkeypatch) -> None:
    calls = []

    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                output_text='{"scenario_id": "scenario-001"}',
                usage=SimpleNamespace(
                    input_tokens=100,
                    input_tokens_details=SimpleNamespace(cached_tokens=25),
                    output_tokens=50,
                ),
            )

    class FakeOpenAI:
        def __init__(self, *, api_key: str, timeout: float) -> None:
            assert api_key == "test-key"
            assert timeout == 300.0
            self.responses = FakeResponses()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    client = OpenAIResponsesJsonClient(openai_factory=FakeOpenAI)

    result = client.create_json(
        model="gpt-5",
        system_prompt="Return JSON.",
        payload={"scenario_id": "scenario-001"},
        schema={"type": "object"},
        cache_key="sha256:cache",
    )

    assert result.data == {"scenario_id": "scenario-001"}
    assert result.usage.input_tokens == 100
    assert result.usage.cached_input_tokens == 25
    assert result.usage.output_tokens == 50
    assert calls[0]["model"] == "gpt-5"
    assert calls[0]["prompt_cache_key"] == "sha256:cache"
    assert calls[0]["text"]["format"]["type"] == "json_schema"


def test_responses_json_client_salvages_leading_json_object(monkeypatch) -> None:
    class FakeResponses:
        def create(self, **_kwargs):
            return SimpleNamespace(
                output_text='{"scenario_id": "scenario-001"}\n{"diagnostic": true}',
                usage=SimpleNamespace(input_tokens=1, output_tokens=2),
            )

    class FakeOpenAI:
        def __init__(self, *, api_key: str, timeout: float) -> None:
            assert api_key == "test-key"
            assert timeout == 45.0
            self.responses = FakeResponses()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_REQUEST_TIMEOUT_SECONDS", "45")
    client = OpenAIResponsesJsonClient(openai_factory=FakeOpenAI)

    result = client.create_json(
        model="gpt-5",
        system_prompt="Return JSON.",
        payload={"scenario_id": "scenario-001"},
        schema={"type": "object"},
    )

    assert result.data == {"scenario_id": "scenario-001"}
