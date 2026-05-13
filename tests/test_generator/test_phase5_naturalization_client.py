"""Unit tests for Phase5NaturalizationClient adapter.

The adapter wraps :func:`run_naturalization` and converts its
:class:`NaturalizationPatch` result into the publish-script dict
shape expected by ``scripts/publish_phase5_scenarios.py``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clawsocialarena.generator.phase5_naturalization import Phase5NaturalizationClient
from clawsocialarena.llm.costing import TokenUsage
from clawsocialarena.llm.openai_client import OpenAIJsonResult


class _FakeJsonClient:
    """Fake JsonClient that returns a fixed NaturalizationPatch response."""

    def __init__(self, *, agent_ids: list[str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._agent_ids = agent_ids or ["agent-1"]

    def create_json(
        self,
        *,
        model: str,
        system_prompt: str,
        payload: dict[str, Any],
        schema: dict[str, Any] | None = None,
        cache_key: str | None = None,
    ) -> OpenAIJsonResult:
        self.calls.append({
            "model": model,
            "payload": payload,
            "cache_key": cache_key,
        })
        persona_notes = {
            agent_id: f"You are acting as {agent_id}."
            for agent_id in self._agent_ids
        }
        return OpenAIJsonResult(
            data={
                "scenario_id": payload.get("scenario_id", "test-scenario"),
                "world_patch": {
                    "files": {},
                    "databases": {},
                },
                "scenario_patch": {
                    "opening_message": "Please complete the task.",
                    "persona_notes": persona_notes,
                },
                "construction_metadata": {
                    "naturalization_mode": "llm",
                    "naturalization_model": model,
                    "prompt_hash": "placeholder",
                    "cache_key": "placeholder",
                },
            },
            usage=TokenUsage(
                model=model,
                input_tokens=800,
                cached_input_tokens=200,
                output_tokens=400,
            ),
        )


def _make_base_dir(tmp_path: Path, *, family_id: str = "tau2_retail") -> Path:
    """Write the three input files that the adapter reads."""
    base = tmp_path / "base"
    base.mkdir()

    scenario = {
        "scenario_id": "test-scenario-001",
        "family_id": family_id,
        "agents": [
            {
                "agent_id": "agent-1",
                "system_prompt_template": "You act for Alice (agent-1).",
            }
        ],
        "opening_message": "Hello, please proceed.",
    }
    (base / "scenario.json").write_text(
        json.dumps(scenario, indent=2), encoding="utf-8"
    )

    gt = {
        "construction_manifest": {"family_id": family_id},
        "evaluation_criteria": {
            "env_assertions": [],
            "actions": [],
        },
        "resource_manifest": {},
        "attack_plan": {},
        "invariants": {},
    }
    (base / "scenario.gt.json").write_text(
        json.dumps(gt, indent=2), encoding="utf-8"
    )

    (base / "family_pack_context.json").write_text("{}", encoding="utf-8")

    return base


def test_naturalize_returns_required_keys(tmp_path: Path) -> None:
    """naturalize() must return all four required keys."""
    base = _make_base_dir(tmp_path)
    fake_client = _FakeJsonClient(agent_ids=["agent-1"])
    adapter = Phase5NaturalizationClient(model="gpt-5", client=fake_client)

    result = adapter.naturalize(base_dir=base)

    assert "personas" in result
    assert "rendered_scenario_overrides" in result
    assert "tokens_used" in result
    assert "naturalization_status" in result
    assert result["naturalization_status"] == "ok"


def test_naturalize_personas_shape(tmp_path: Path) -> None:
    """Each persona entry must have system_md and tools_json."""
    base = _make_base_dir(tmp_path)
    fake_client = _FakeJsonClient(agent_ids=["agent-1"])
    adapter = Phase5NaturalizationClient(model="gpt-5", client=fake_client)

    result = adapter.naturalize(base_dir=base)

    personas = result["personas"]
    assert isinstance(personas, dict)
    assert "agent-1" in personas
    entry = personas["agent-1"]
    assert "system_md" in entry
    assert "tools_json" in entry
    assert isinstance(entry["system_md"], str)
    assert isinstance(entry["tools_json"], dict)
    assert "agent-1" in entry["system_md"]


def test_naturalize_rendered_scenario_overrides_carries_opening_message(
    tmp_path: Path,
) -> None:
    """rendered_scenario_overrides must contain opening_message."""
    base = _make_base_dir(tmp_path)
    fake_client = _FakeJsonClient(agent_ids=["agent-1"])
    adapter = Phase5NaturalizationClient(model="gpt-5", client=fake_client)

    result = adapter.naturalize(base_dir=base)

    overrides = result["rendered_scenario_overrides"]
    assert isinstance(overrides, dict)
    assert "opening_message" in overrides
    assert isinstance(overrides["opening_message"], str)


def test_naturalize_tokens_used_shape(tmp_path: Path) -> None:
    """tokens_used must use prompt/completion key names for the publish script."""
    base = _make_base_dir(tmp_path)
    fake_client = _FakeJsonClient(agent_ids=["agent-1"])
    adapter = Phase5NaturalizationClient(model="gpt-5", client=fake_client)

    result = adapter.naturalize(base_dir=base)

    tokens = result["tokens_used"]
    assert isinstance(tokens, dict)
    assert "prompt" in tokens
    assert "completion" in tokens
    # input_tokens=800, cached_input_tokens=200 → prompt=1000; output_tokens=400
    assert tokens["prompt"] == 1000
    assert tokens["completion"] == 400


def test_naturalize_falls_back_to_gt_family_id(tmp_path: Path) -> None:
    """When scenario.json lacks family_id, the adapter reads from construction_manifest."""
    base = tmp_path / "base"
    base.mkdir()

    scenario_no_fid = {
        "scenario_id": "test-scenario-002",
        "agents": [{"agent_id": "agent-1", "system_prompt_template": "Act for Alice."}],
        "opening_message": "Please proceed.",
    }
    (base / "scenario.json").write_text(json.dumps(scenario_no_fid), encoding="utf-8")
    (base / "scenario.gt.json").write_text(json.dumps({
        "construction_manifest": {"family_id": "tau2_retail"},
        "evaluation_criteria": {"env_assertions": [], "actions": []},
        "resource_manifest": {},
    }), encoding="utf-8")
    (base / "family_pack_context.json").write_text("{}", encoding="utf-8")

    fake_client = _FakeJsonClient(agent_ids=["agent-1"])
    adapter = Phase5NaturalizationClient(model="gpt-5", client=fake_client)
    result = adapter.naturalize(base_dir=base)
    assert result["naturalization_status"] == "ok"


def test_naturalize_passes_model_to_llm(tmp_path: Path) -> None:
    """The adapter forwards the configured model to the underlying LLM client."""
    base = _make_base_dir(tmp_path)
    fake_client = _FakeJsonClient(agent_ids=["agent-1"])
    adapter = Phase5NaturalizationClient(model="gpt-test-model", client=fake_client)

    adapter.naturalize(base_dir=base)

    assert fake_client.calls, "no calls were made"
    assert fake_client.calls[0]["model"] == "gpt-test-model"
