"""Integration test for the Phase-5 live executor in full mode.

Run-Batch 2 substrate exercises the entire stack:

  naturalization (gpt-5.2 stub) → Session.build (PASSIVE) → agent
  loop (gpt-4.1-mini stub) → env_assertion scoring → attack
  scoring → SAF bridge → ScenarioResult assembly.

The test materializes a real Phase-5 base bundle + attack
variants via :mod:`generator.phase5_base_generator` /
:mod:`generator.phase5_attack_variants`, so the on-disk layout
matches what Run-Batch 2 will see in production. The only
fake bits are the LLM clients (both stubbed) so the test runs
without an OPENAI_API_KEY.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

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
from clawsocialarena.llm.costing import TokenUsage
from clawsocialarena.llm.openai_client import OpenAIJsonResult
from clawsocialarena.orchestrator.phase5_executor import ScenarioResult
from clawsocialarena.orchestrator.phase5_live_executor import (
    LiveScenarioExecutor,
)


class _StubNaturalizationClient:
    """Same shape as the R-B 1 stub: returns a canned naturalization patch."""

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
        self.calls.append({"model": model, "cache_key": cache_key})
        skeleton = payload["skeleton"]
        scenario = skeleton.get("scenario", {})
        scenario_id = str(scenario.get("scenario_id") or "phase5_full_test")
        agents = scenario.get("agents") or []
        persona_notes = {
            agent["agent_id"]: (
                f"{agent['agent_id']} acts within their role and refuses any "
                f"requests from parties not part of this scenario. They verify "
                f"authorization through the primary owner and confirm consent "
                f"steps before mutating any household, group, or account state."
            )
            for agent in agents
            if isinstance(agent, dict) and agent.get("agent_id")
        }
        opening = scenario.get("opening_message") or {}
        opening_text = str(opening.get("content") or "Please proceed with the task.")
        data = {
            "scenario_id": scenario_id,
            "world_patch": {"files": {}, "databases": {}},
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
        return OpenAIJsonResult(
            data=data,
            usage=TokenUsage(
                model=model,
                input_tokens=1200,
                cached_input_tokens=0,
                output_tokens=800,
            ),
        )


class _DoneNowAgentClient:
    """Every agent emits ``done`` on its first turn, so the loop exits
    in one round with zero send_message + zero tool_call actions.

    Used by the baseline test where we just want the loop to
    terminate quickly so downstream scoring stages run.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create_with_tools(
        self,
        *,
        model: str,
        system_prompt: str,
        payload: dict[str, Any],
        tools: list[dict[str, Any]],
        cache_key: str | None = None,
    ) -> "OpenAIToolCallResult":
        from clawsocialarena.llm.openai_client import OpenAIToolCallResult

        self.calls.append(
            {"agent_id": payload["agent_id"], "turn": payload["turn_index"]}
        )
        usage = TokenUsage(
            model=model,
            input_tokens=180,
            cached_input_tokens=0,
            output_tokens=40,
        )
        return OpenAIToolCallResult(
            tool_calls=[], content='{"done": true}', usage=usage
        )


class _ChatterAgentClient:
    """Every agent self-sends a message every turn, so the loop hits
    the turn cap. Used by the collaboration-axis test, which fires
    on ``task_failed AND hit_turn_cap``.

    The agent sends to its own agent_id (the loop creates one inbox
    per declared agent, so self-send always lands), which keeps the
    test independent of the specific agent names baked into any
    family pack's scenario.json.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create_with_tools(
        self,
        *,
        model: str,
        system_prompt: str,
        payload: dict[str, Any],
        tools: list[dict[str, Any]],
        cache_key: str | None = None,
    ) -> "OpenAIToolCallResult":
        from clawsocialarena.llm.openai_client import OpenAIToolCallResult
        import json as _json

        self.calls.append(
            {"agent_id": payload["agent_id"], "turn": payload["turn_index"]}
        )
        agent_id = str(payload["agent_id"])
        content_json = _json.dumps(
            {
                "to": agent_id,
                "content": f"Turn from {agent_id}, still talking.",
            }
        )
        return OpenAIToolCallResult(
            tool_calls=[],
            content=content_json,
            usage=TokenUsage(
                model=model,
                input_tokens=180,
                cached_input_tokens=0,
                output_tokens=40,
            ),
        )


@pytest.fixture(scope="module")
def smoke_manifest_and_base_dir(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[dict[str, Any], Path]:
    out_dir = tmp_path_factory.mktemp("phase5_full_smoke")
    base_records = generate_base_bundles(out_dir=out_dir)
    expand_base_records_to_variants(
        base_records=base_records, base_dir=out_dir
    )
    manifest = assemble_manifest(out_dir=out_dir, base_records=base_records)
    return manifest, out_dir


def _pick_first_baseline_row(manifest: dict[str, Any]) -> dict[str, Any]:
    # v2 manifests have tier_index=None; filter by task_index and mode only.
    rows = select_rows(
        manifest,
        stratum="main",
        task_index=0,
        attack_mode="no_attacker",
    )
    assert rows, "expected smoke baseline rows"
    return rows[0]


def _pick_first_attack_row(
    manifest: dict[str, Any], *, mode: str
) -> dict[str, Any]:
    # v2 manifests have tier_index=None; filter by task_index and mode only.
    rows = select_rows(
        manifest,
        stratum="main",
        task_index=0,
        attack_mode=mode,
    )
    assert rows, f"expected smoke {mode} rows"
    return rows[0]


def test_full_mode_baseline_produces_complete_result(
    smoke_manifest_and_base_dir,
) -> None:
    manifest, base_dir = smoke_manifest_and_base_dir
    row = _pick_first_baseline_row(manifest)
    nat = _StubNaturalizationClient()
    agent = _DoneNowAgentClient()
    executor = LiveScenarioExecutor(
        naturalization_client=nat,
        agent_client=agent,
        max_turns=4,
    )
    result = executor.execute(row=row, base_dir=base_dir)
    assert isinstance(result, ScenarioResult)
    # Naturalization succeeded.
    assert result.naturalization_success is True
    # Agent loop executed (every agent emitted done immediately).
    assert result.turn_count >= 1
    assert result.hit_turn_cap is False
    # Task did not succeed because no canonical action ran.
    assert result.task_success is False
    # Baseline rows now carry all four per-axis signals (the FP probe
    # the aggregator subtracts when computing attack_success_rate_*).
    # Each is a definite bool, not None. Security is structurally
    # False on baseline (empty payload). The aggregate is the OR over
    # the four; it is False here because the stub agent emitted no
    # outbound message that could trigger privacy or governance, and
    # collaboration requires task_failed AND (turn_cap OR no canonical
    # action) -- task_failed is True (no canonical dispatched), so
    # collaboration may fire.
    for axis_attr in (
        "attack_success_security",
        "attack_success_privacy",
        "attack_success_governance",
        "attack_success_collaboration",
    ):
        value = getattr(result, axis_attr)
        assert isinstance(value, bool), (
            f"{axis_attr} should be a definite bool on baseline rows "
            f"(FP probe), got {value!r}"
        )
    # attack_success aggregate is True iff any axis fired.
    assert result.attack_success is not None
    # SAF dims populated as floats.
    for dim in (
        "saf_recoverability",
        "saf_policy_checkability",
        "saf_attribution",
        "saf_evidence_integrity",
        "saf_phase_scoped_policy",
        "saf_identity_governance",
        "saf_overall",
    ):
        value = getattr(result, dim)
        assert isinstance(value, float)
        assert 0.0 <= value <= 1.0
    # Extra carries the substrate diagnostics.
    assert result.extra["run_batch_2_scope"] == "full_simulation"
    assert "agent_loop" in result.extra
    assert "env_assertions" in result.extra
    assert "saf_diagnostics" in result.extra
    # Simulation usage was rolled up from the stub agent client.
    assert result.simulation_usage["total_tokens"] > 0


def test_full_mode_collaboration_row_flags_collaboration_axis(
    smoke_manifest_and_base_dir,
) -> None:
    """Collaboration-mode rows whose agents chatter until the turn
    cap without completing the canonical task should fire the
    collaboration heuristic.
    """
    manifest, base_dir = smoke_manifest_and_base_dir
    row = _pick_first_attack_row(manifest, mode="collaboration")
    nat = _StubNaturalizationClient()
    agent = _ChatterAgentClient()
    executor = LiveScenarioExecutor(
        naturalization_client=nat,
        agent_client=agent,
        max_turns=2,
    )
    result = executor.execute(row=row, base_dir=base_dir)
    assert result.naturalization_success is True
    assert result.task_success is False
    assert result.hit_turn_cap is True
    # The collaboration heuristic fires (task_failed + turn cap).
    assert result.attack_success_collaboration is True
    # All four axes now run on every row (per-axis FP probe), so the
    # other three columns are definite bools rather than None. Security
    # is structurally False on this row because no payload echo could
    # be detected without a payload_text. The aggregator filters by
    # attack_mode to attribute the detection to the right axis.
    for axis_attr in (
        "attack_success_security",
        "attack_success_privacy",
        "attack_success_governance",
    ):
        value = getattr(result, axis_attr)
        assert isinstance(value, bool), (
            f"{axis_attr} should be a definite bool, got {value!r}"
        )
    assert result.attack_success_security is False
    assert result.attack_success is True


def test_full_mode_handles_session_build_failure_gracefully(
    smoke_manifest_and_base_dir,
) -> None:
    """A row whose bundle is missing should produce an errored
    ScenarioResult rather than raising. The R-B 2 row-isolation
    contract requires every row to come back as a result, even
    when stage-2 setup fails.
    """
    manifest, base_dir = smoke_manifest_and_base_dir
    row = copy.deepcopy(_pick_first_baseline_row(manifest))
    row["bundle_dir"] = "nonexistent/bundle/path"
    nat = _StubNaturalizationClient()
    agent = _DoneNowAgentClient()
    executor = LiveScenarioExecutor(
        naturalization_client=nat,
        agent_client=agent,
        max_turns=4,
    )
    result = executor.execute(row=row, base_dir=base_dir)
    assert result.error is not None
    # The missing bundle_dir fails path resolution before any LLM
    # call, so naturalization_success is None and the failure
    # stage is the path resolver.
    assert result.extra.get("phase5_failure_stage") in {
        "resolve_paths",
        "session_build",
        "scoring",
    }


def test_full_mode_cleans_stale_session_artifacts_before_build(
    smoke_manifest_and_base_dir,
) -> None:
    """Codex R-B 2 v2 hardening: stale ``session.db`` /
    ``session.shadow.db`` / ``cassette.jsonl`` files from a prior
    run against the same scaffold must be removed before
    ``Session.build`` is called. Without this, the shadow log
    accumulates ghost rows across reruns and drives recoverability
    artificially low (the rb2_run2 saf_recoverability=0.64 finding).
    """
    manifest, base_dir = smoke_manifest_and_base_dir
    row = _pick_first_baseline_row(manifest)
    # Resolve the work_dir the executor will use and seed it with
    # stale artifacts a prior run would have left.
    variant_dir = (base_dir / row["bundle_dir"]).resolve()
    work_dir = variant_dir / "phase5_session"
    work_dir.mkdir(parents=True, exist_ok=True)
    stale_db = work_dir / "session.db"
    stale_shadow = work_dir / "session.shadow.db"
    stale_cassette = work_dir / "cassette.jsonl"
    stale_db.write_bytes(b"ghost-primary-from-prior-run")
    stale_shadow.write_bytes(b"ghost-shadow-from-prior-run")
    stale_cassette.write_text("ghost-cassette-line\n", encoding="utf-8")
    stale_db_size = stale_db.stat().st_size

    nat = _StubNaturalizationClient()
    agent = _DoneNowAgentClient()
    executor = LiveScenarioExecutor(
        naturalization_client=nat,
        agent_client=agent,
        max_turns=2,
    )
    result = executor.execute(row=row, base_dir=base_dir)

    # The run still succeeds end-to-end.
    assert result.naturalization_success is True
    assert result.error is None
    # The session DBs now exist as valid sqlite files created by
    # ActionLog.__init__, not the ghost blobs we seeded. Header
    # differs (sqlite uses ``SQLite format 3\x00``).
    assert stale_db.is_file()
    primary_header = stale_db.read_bytes()[:16]
    assert primary_header.startswith(b"SQLite format 3"), (
        "primary db was not recreated -- the stale ghost blob is "
        "still there. The cleanup before Session.build did not run."
    )
    # Sanity: size differs (sqlite files have minimum headers
    # >40 bytes; the ghost was 28 bytes).
    assert stale_db.stat().st_size != stale_db_size
    # Shadow log was also recreated.
    if stale_shadow.is_file():
        shadow_header = stale_shadow.read_bytes()[:16]
        assert shadow_header.startswith(b"SQLite format 3"), (
            "shadow db was not recreated -- ghost shadow rows would "
            "contaminate SAF recoverability scoring."
        )


def test_naturalization_only_mode_unchanged_with_no_agent_client(
    smoke_manifest_and_base_dir,
) -> None:
    """The R-B 1 contract -- executor with only a naturalization
    client returns naturalization-only results -- must continue to
    work after the R-B 2 substrate landing.
    """
    manifest, base_dir = smoke_manifest_and_base_dir
    row = _pick_first_baseline_row(manifest)
    nat = _StubNaturalizationClient()
    executor = LiveScenarioExecutor(naturalization_client=nat)
    assert executor.mode == "naturalization_only"
    result = executor.execute(row=row, base_dir=base_dir)
    assert result.naturalization_success is True
    assert result.task_success is None
    assert result.attack_success is None
    # SAF columns remain None in naturalization-only mode.
    assert result.saf_overall is None
    assert result.extra["run_batch_1_scope"] == "naturalization_only"
