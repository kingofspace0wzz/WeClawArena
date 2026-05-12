"""Tests for the Phase-5 live executor (Run-Batch 1 wiring).

The live executor's job in Run-Batch 1 is to take a manifest row,
naturalize the underlying base bundle via gpt-5.2, and return a
``ScenarioResult`` with naturalization usage rolled up. Agent-loop
simulation lands in later run-batches.

These tests inject a fake JsonClient so the executor's wiring can be
validated without OPENAI_API_KEY. The real Run-Batch 1 invocation is
a separate shell command (live LLM calls) reported in
``BATCH_01_smoke_REPORT.md``.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from clawsocialarena.generator.cell_allocation import all_cells
from clawsocialarena.generator.phase5_attack_variants import (
    expand_base_records_to_variants,
)
from clawsocialarena.generator.phase5_base_generator import (
    generate_base_bundles,
)
from clawsocialarena.generator.phase5_manifest import (
    assemble_manifest,
    select_rows,
)
from clawsocialarena.llm.openai_client import OpenAIJsonResult
from clawsocialarena.orchestrator.phase5_executor import ScenarioResult
from clawsocialarena.orchestrator.phase5_live_executor import (
    LiveScenarioExecutor,
)


class _StubJsonClient:
    """Returns a canned naturalization payload that passes the schema."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create_json(
        self,
        *,
        model: str,
        system_prompt: str,
        payload: dict[str, Any],
        schema: dict[str, Any] | None = None,
        cache_key: str | None = None,
    ) -> OpenAIJsonResult:
        self.calls.append(
            {
                "model": model,
                "payload": copy.deepcopy(payload),
                "cache_key": cache_key,
            }
        )
        skeleton = payload["skeleton"]
        scenario = skeleton.get("scenario", {})
        scenario_id = str(scenario.get("scenario_id") or "stub_scenario")
        # The schema-validation layer of run_naturalization requires
        # one persona note per agent_id. Map every agent to a small,
        # distinctive prose blurb so the quality checks pass.
        agents = scenario.get("agents") or []
        persona_notes = {
            agent["agent_id"]: (
                f"{agent['agent_id']} acts within their role "
                f"in scenario {scenario_id} with care for the household, "
                f"group, account, or proposal context. The agent always "
                f"verifies authorization with the primary owner, confirms "
                f"explicit consent steps, and refuses requests from "
                f"parties not part of this conversation."
            )
            for agent in agents
            if isinstance(agent, dict) and agent.get("agent_id")
        }
        opening = scenario.get("opening_message") or {}
        opening_text = str(opening.get("content") or "Please proceed.")
        if not opening_text.strip():
            opening_text = "Please proceed."
        data = {
            "scenario_id": scenario_id,
            "world_patch": {
                "files": {},
                "databases": {},
            },
            "scenario_patch": {
                "opening_message": opening_text,
                "persona_notes": persona_notes,
            },
            "construction_metadata": {
                "naturalization_mode": "llm",
                "naturalization_model": model,
                "prompt_hash": "sha256:stub",
                "cache_key": cache_key or "sha256:stub",
            },
            "usage": {
                "model": model,
                "input_tokens": 1200,
                "cached_input_tokens": 0,
                "output_tokens": 800,
            },
        }
        usage = {
            "model": model,
            "input_tokens": 1200,
            "cached_input_tokens": 0,
            "output_tokens": 800,
        }
        from clawsocialarena.llm.costing import TokenUsage

        return OpenAIJsonResult(data=data, usage=TokenUsage(**usage))


@pytest.fixture(scope="module")
def manifest_and_base_dir(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[dict[str, Any], Path]:
    out_dir = tmp_path_factory.mktemp("phase5_live_smoke")
    base_records = generate_base_bundles(out_dir=out_dir)
    expand_base_records_to_variants(
        base_records=base_records, base_dir=out_dir
    )
    manifest = assemble_manifest(out_dir=out_dir, base_records=base_records)
    return manifest, out_dir


def test_live_executor_naturalizes_baseline_row(
    manifest_and_base_dir,
) -> None:
    manifest, base_dir = manifest_and_base_dir
    smoke = select_rows(
        manifest,
        stratum="main",
        tier_index=1,
        task_index=0,
        attack_mode="no_attacker",
    )
    assert smoke, "expected smoke baseline rows in manifest"
    row = smoke[0]
    stub = _StubJsonClient()
    executor = LiveScenarioExecutor(naturalization_client=stub)
    result = executor.execute(row=row, base_dir=base_dir)
    assert isinstance(result, ScenarioResult)
    assert result.error is None
    # Run-Batch 1 measures naturalization_success only; task_success
    # stays None because the canonical task is not attempted (no
    # agent loop).
    assert result.naturalization_success is True
    assert result.task_success is None
    assert result.attack_success is None
    assert result.naturalization_usage["total_tokens"] == 2000
    assert result.simulation_usage == {}
    assert len(stub.calls) == 1
    assert stub.calls[0]["model"] == "gpt-5.2"


def test_live_executor_handles_attack_variant_rows(
    manifest_and_base_dir,
) -> None:
    """Attack rows should naturalize against the BASE bundle, not the
    per-variant scenario.json that already has the payload injected.
    The 5 variants of one base task should share the same skeleton
    contents (one naturalization call per base, not per variant).
    """
    manifest, base_dir = manifest_and_base_dir
    smoke = select_rows(
        manifest, stratum="main", tier_index=1, task_index=0
    )
    by_base: dict[str, list[dict[str, Any]]] = {}
    for row in smoke:
        by_base.setdefault(row["base_scenario_id"], []).append(row)
    # Pick one base with all 5 modes and confirm every mode naturalizes
    # without error against the same base bundle.
    base_id, rows = next(iter(by_base.items()))
    assert len(rows) == 5
    stub = _StubJsonClient()
    executor = LiveScenarioExecutor(naturalization_client=stub)
    for row in rows:
        result = executor.execute(row=row, base_dir=base_dir)
        assert result.error is None, f"{row['attack_mode']} errored: {result.error}"
        assert result.naturalization_success is True
        assert result.task_success is None
    # Five rows but only one base, so 5 calls with the same skeleton
    # payload (gpt-5.2 cache_key will dedupe in production).
    assert len(stub.calls) == 5
    skeleton_ids = {
        call["payload"]["skeleton"]["scenario"]["scenario_id"]
        for call in stub.calls
    }
    assert len(skeleton_ids) == 1, "5 variants must share one base skeleton"


def test_live_executor_raises_on_supplementary_rows() -> None:
    """Supplementary rows must surface a clear error in Run-Batch 1
    so a misconfigured invocation does not silently process them.
    """
    row = {
        "variant_id": "supp-na-00-saf_attribution_collision",
        "stratum": "supplementary",
        "sub_stratum": "named_audit",
        "recipe": "named_audit_case",
        "family_id": "tau2_retail",
    }
    executor = LiveScenarioExecutor(naturalization_client=_StubJsonClient())
    with pytest.raises(NotImplementedError) as excinfo:
        executor.execute(row=row, base_dir=Path("/tmp"))
    assert "Run-Batch 5" in str(excinfo.value)


def test_live_executor_per_family_coverage(manifest_and_base_dir) -> None:
    """Every registered family must naturalize cleanly in Run-Batch 1.
    Iterate one row per family at task=0, tier=1, no_attacker and
    confirm none errors.
    """
    manifest, base_dir = manifest_and_base_dir
    smoke = select_rows(
        manifest,
        stratum="main",
        tier_index=1,
        task_index=0,
        attack_mode="no_attacker",
    )
    family_to_row: dict[str, dict[str, Any]] = {}
    for row in smoke:
        family_to_row.setdefault(row["family_id"], row)
    families_in_smoke = set(family_to_row.keys())
    families_in_allocation = {c.family_id for c in all_cells()}
    assert families_in_smoke == families_in_allocation, (
        f"smoke missing families: {families_in_allocation - families_in_smoke}"
    )
    stub = _StubJsonClient()
    executor = LiveScenarioExecutor(naturalization_client=stub)
    for family_id, row in family_to_row.items():
        result = executor.execute(row=row, base_dir=base_dir)
        assert result.error is None, (
            f"family {family_id} errored: {result.error}"
        )


def test_live_executor_records_metadata_extras(
    manifest_and_base_dir,
) -> None:
    manifest, base_dir = manifest_and_base_dir
    smoke = select_rows(
        manifest,
        stratum="main",
        tier_index=1,
        task_index=0,
        attack_mode="no_attacker",
    )
    stub = _StubJsonClient()
    executor = LiveScenarioExecutor(naturalization_client=stub)
    result = executor.execute(row=smoke[0], base_dir=base_dir)
    assert "naturalization_metadata" in result.extra
    assert result.extra["run_batch_1_scope"] == "naturalization_only"
    assert result.extra["naturalized_scenario_id"]


def test_errored_result_preserves_raw_usage_in_extra(
    manifest_and_base_dir,
) -> None:
    """Codex Run-Batch 1 audit-precision regression: when
    naturalization fails its quality checks, the executor must still
    persist the token usage (under ``extra.raw_usage``) so the
    cost rollup can include the row.
    """
    from clawsocialarena.generator.naturalization import (
        NaturalizationValidationError,
    )
    from clawsocialarena.llm.costing import TokenUsage

    manifest, base_dir = manifest_and_base_dir
    smoke = select_rows(
        manifest,
        stratum="main",
        tier_index=1,
        task_index=0,
        attack_mode="no_attacker",
    )

    class _AlwaysRaisesClient(_StubJsonClient):
        def create_json(self, **kwargs):  # type: ignore[override]
            # Raise the same error the sanitizer would have raised
            # against the real client, so the executor's
            # NaturalizationValidationError path runs end-to-end.
            raise NaturalizationValidationError(
                "synthetic quality failure",
                usage=TokenUsage(
                    model=kwargs.get("model", "gpt-5.2"),
                    input_tokens=2696,
                    cached_input_tokens=0,
                    output_tokens=882,
                ),
                raw_data={},
            )

    executor = LiveScenarioExecutor(naturalization_client=_AlwaysRaisesClient())
    result = executor.execute(row=smoke[0], base_dir=base_dir)
    assert result.error is not None
    assert "synthetic quality failure" in result.error
    # Aggregated usage is present.
    assert result.naturalization_usage["prompt_tokens"] == 2696
    assert result.naturalization_usage["completion_tokens"] == 882
    # Raw usage breakdown (with cached split) is also preserved for
    # downstream cost rollup.
    raw = result.extra.get("raw_usage") or {}
    assert raw.get("input_tokens") == 2696
    assert raw.get("output_tokens") == 882
    assert raw.get("cached_input_tokens") == 0
