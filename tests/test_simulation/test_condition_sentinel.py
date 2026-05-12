import json
from pathlib import Path

from clawsocialarena.simulation.condition_sentinel import (
    run_condition_sentinel_batch,
    sentinel_scenario_id,
)


def test_run_condition_sentinel_batch_copies_bundles_and_tracks_conditions(
    tmp_path: Path,
) -> None:
    source_batch = tmp_path / "source-batch"
    _write_source_scenario(source_batch, "source-a-no_attacker")
    _write_json(
        source_batch / "batch_report.json",
        {
            "batch_id": "source-batch",
            "accepted_scenario_ids": ["source-a-no_attacker"],
            "usage": {
                "construction": {"model": "gpt-5.2"},
                "simulation": {"model": "gpt-4.1-mini"},
            },
        },
    )
    seen_conditions: list[str] = []

    def fake_runner(
        *,
        scenario_id: str,
        bundle_dir: Path,
        agent_model: str,
        condition: str,
    ) -> dict:
        seen_conditions.append(condition)
        scorecard_path = bundle_dir / "run" / "run_scorecard.json"
        _write_scorecard(scorecard_path, scenario_id=scenario_id, condition=condition)
        return {
            "scenario_id": scenario_id,
            "status": "simulation_passed",
            "scorecard_path": str(scorecard_path),
            "usage": {
                "model": agent_model,
                "input_tokens": 10,
                "cached_input_tokens": 2,
                "output_tokens": 3,
            },
            "error": "",
        }

    report = run_condition_sentinel_batch(
        source_batch_dir=source_batch,
        batch_id="sentinel-0001",
        out_dir=tmp_path / "batches",
        scenario_ids=["source-a-no_attacker"],
        conditions=["baseline", "enforce"],
        simulation_runner=fake_runner,
    )

    assert seen_conditions == ["baseline", "enforce"]
    assert report.construction_unit == "condition_sentinel_run"
    assert report.condition == "mixed"
    assert report.condition_counts == {"baseline": 1, "enforce": 1}
    assert report.accepted_count == 2
    assert report.usage.construction.input_tokens == 0
    assert report.usage.simulation.input_tokens == 20
    assert report.scenario_ids == [
        sentinel_scenario_id("source-a-no_attacker", "baseline"),
        sentinel_scenario_id("source-a-no_attacker", "enforce"),
    ]
    selection = json.loads(
        (
            tmp_path
            / "batches"
            / "sentinel-0001"
            / "batch_selection.json"
        ).read_text(encoding="utf-8")
    )
    assert selection["selection_strategy"] == "condition-sentinel"
    assert selection["conditions"] == ["baseline", "enforce"]
    assert selection["scenario_condition_pairs"][0] == {
        "scenario_id": "source-a-no_attacker--baseline",
        "source_scenario_id": "source-a-no_attacker",
        "condition": "baseline",
    }


def _write_source_scenario(batch_dir: Path, scenario_id: str) -> None:
    scenario_dir = batch_dir / "scenarios" / scenario_id
    bundle_dir = scenario_dir / "bundle"
    bundle_dir.mkdir(parents=True)
    _write_json(
        scenario_dir / "skeleton_payload.json",
        {
            "scenario_id": scenario_id,
            "index_row": {
                "scenario_id": scenario_id,
                "base_task_id": "source-a",
                "category": "CU",
                "family": "scheduling",
                "designed_difficulty_tier": "easy",
                "attack_mode": "no_attacker",
            },
        },
    )
    _write_json(
        bundle_dir / "scenario.json",
        {
            "scenario_id": scenario_id,
            "category": "CU",
            "task_family": "scheduling",
            "agents": [],
            "initial_state": {},
            "max_turns": 1,
            "opening_message": {"from": "a", "to": "b", "content": "x"},
        },
    )
    _write_json(
        bundle_dir / "scenario.gt.json",
        {
            "scenario_id": scenario_id,
            "terminal_predicate": {},
        },
    )
    (bundle_dir / "docker-compose.yml").write_text(
        "services:\n"
        "  gateway:\n"
        "    command:\n"
        "      - --condition\n"
        "      - passive\n",
        encoding="utf-8",
    )


def _write_scorecard(path: Path, *, scenario_id: str, condition: str) -> None:
    if condition == "baseline":
        transcript_path = path.parent / "baseline_transcript.jsonl"
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text('{"event_type":"final_state"}\n', encoding="utf-8")
    _write_json(
        path,
        {
            "scenario_id": scenario_id,
            "task": {"tsr": 1.0, "partial_credit": {}},
            "saf": {
                "dims": {"recoverability": 1.0},
                "passes": {"recoverability": True},
                "overall": 1.0,
                "diagnostics": {
                    "applicability": {"recoverability": condition != "baseline"},
                    "not_applicable": condition == "baseline",
                },
            },
            "diagnostics": {
                "task_tool_evidence": {"passed": True},
            },
            "privacy": {
                "leak_rates": {},
                "privacy_attack_success": False,
                "resource_tool_violation_success": False,
            },
            "security": {"asr": 0.0},
            "governance": {"governance_violation_rate": 0.0},
            "meta": {"condition": condition},
        },
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
