import hashlib
import json
from pathlib import Path

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.shadow_log import ShadowLog
from clawsocialarena.scenario.models import GTBundle
from clawsocialarena.simulation.reevaluate import reevaluate_existing_batch
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


def _append_message(log: ActionLog, *, agent_id: str, action_id: str) -> None:
    record = ActionRecord(
        action_id=action_id,
        prev_hash=log.head_hash(agent_id),
        agent_id=agent_id,
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-05-06T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={
            "recipient_id": "agent-peer",
            "content": "Frozen trajectory message.",
        },
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )
    log.append(record)


def _minimal_gt(scenario_id: str) -> GTBundle:
    return GTBundle(
        scenario_id=scenario_id,
        canonical_action_stream=[],
        phase_schedule=[],
        policies={"flat": [], "phase_scoped": []},
        attribution_dag={"nodes": [], "edges": []},
        integrity_requirements={},
        terminal_predicate={"type": "none"},
        invariants={},
    )


def _write_frozen_batch(batch_dir: Path) -> None:
    scenario_id = "scenario-001-no_attacker"
    scenario_out_dir = batch_dir / "scenarios" / scenario_id
    run_dir = scenario_out_dir / "bundle" / "run"
    run_dir.mkdir(parents=True)

    gt = _minimal_gt(scenario_id)
    (scenario_out_dir / "bundle" / "scenario.gt.json").write_text(
        gt.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (scenario_out_dir / "bundle" / "scenario.json").write_text(
        json.dumps(
            {
                "scenario_id": scenario_id,
                "category": "CU",
                "task_family": "consensus",
                "agents": [],
            }
        ),
        encoding="utf-8",
    )
    (scenario_out_dir / "skeleton_payload.json").write_text(
        json.dumps(
            {
                "index_row": {
                    "scenario_id": scenario_id,
                    "base_task_id": "scenario-001",
                    "category": "CU",
                    "family": "consensus",
                    "attack_mode": "no_attacker",
                }
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "cassette.jsonl").write_text(
        '{"kind":"outbound_message"}\n',
        encoding="utf-8",
    )

    primary = ActionLog(run_dir / "action_log.db")
    shadow = ShadowLog(run_dir / "action_log.shadow.db")
    _append_message(primary, agent_id="agent-a", action_id="act-1")
    _append_message(shadow, agent_id="agent-a", action_id="act-1")

    stale_scorecard = {
        "scenario_id": scenario_id,
        "task": {"tsr": 0.0, "partial_credit": {}},
        "saf": {"dims": {}, "passes": {}, "overall": 0.0},
        "diagnostics": {},
        "security": {"asr": 0.0, "prop_depth": 0.0, "tiua": 1.0},
        "privacy": {"leak_rates": {}, "privacy_attack_success": False},
        "governance": {"governance_violation_rate": 0.0},
        "meta": {
            "model": "gpt-4.1-mini",
            "condition": "passive",
            "accepted_task_failure": True,
            "accepted_attack_failure": True,
        },
    }
    (run_dir / "run_scorecard.json").write_text(
        json.dumps(stale_scorecard),
        encoding="utf-8",
    )
    (run_dir / "simulation_report.json").write_text(
        json.dumps(
            {
                "scenario_id": scenario_id,
                "status": "simulation_passed",
                "turn_cap_reached": False,
                "done": True,
                "history": [],
                "error": "",
            }
        ),
        encoding="utf-8",
    )
    (scenario_out_dir / "simulation_result.json").write_text(
        json.dumps(
            {
                "scenario_id": scenario_id,
                "status": "simulation_passed",
                "scorecard_path": str(run_dir / "run_scorecard.json"),
                "usage": {
                    "model": "gpt-4.1-mini",
                    "input_tokens": 10,
                    "cached_input_tokens": 0,
                    "output_tokens": 2,
                },
                "error": "",
            }
        ),
        encoding="utf-8",
    )
    (batch_dir / "batch_selection.json").write_text(
        json.dumps(
            {
                "batch_id": "batch-0001",
                "selection_strategy": "category-sweep",
                "sweep_index": 0,
                "scenario_ids": [scenario_id],
                "base_task_ids": ["scenario-001"],
                "task_distribution": {
                    "selection_strategy": "category-sweep",
                    "sweep_index": 0,
                    "scenario_count": 1,
                    "base_task_count": 1,
                    "category_counts": {"CU": 1},
                    "family_counts": {"consensus": 1},
                    "attack_mode_counts": {"no_attacker": 1},
                },
            }
        ),
        encoding="utf-8",
    )
    (batch_dir / "batch_report.json").write_text(
        json.dumps(
            {
                "batch_id": "batch-0001",
                "scenario_ids": [scenario_id],
                "accepted_scenario_ids": [scenario_id],
                "base_task_ids": ["scenario-001"],
                "accepted_count": 1,
                "failed_count": 0,
                "usage": {
                    "construction": {
                        "model": "gpt-5",
                        "input_tokens": 100,
                        "cached_input_tokens": 0,
                        "output_tokens": 20,
                    },
                    "simulation": {
                        "model": "gpt-4.1-mini",
                        "input_tokens": 10,
                        "cached_input_tokens": 0,
                        "output_tokens": 2,
                    },
                    "construction_estimated_cost_usd": 0.0,
                    "simulation_estimated_cost_usd": 0.0,
                    "total_estimated_cost_usd": 0.0,
                },
                "decision": "STOP_FOR_REVIEW",
            }
        ),
        encoding="utf-8",
    )


def test_reevaluate_existing_batch_recomputes_scorecards_from_frozen_logs(
    tmp_path: Path,
) -> None:
    batch_dir = tmp_path / "batch-0001"
    _write_frozen_batch(batch_dir)

    report = reevaluate_existing_batch(batch_dir, recompute_scorecards=True)

    assert report.accepted_count == 1
    assert report.failed_count == 0
    assert report.task_success_count == 1
    assert report.usage.construction.input_tokens == 100
    assert report.usage.simulation.input_tokens == 10

    scorecard_path = (
        batch_dir
        / "scenarios"
        / "scenario-001-no_attacker"
        / "bundle"
        / "run"
        / "run_scorecard.json"
    )
    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    cassette_bytes = (
        batch_dir
        / "scenarios"
        / "scenario-001-no_attacker"
        / "bundle"
        / "run"
        / "cassette.jsonl"
    ).read_bytes()
    assert scorecard["task"]["tsr"] == 1.0
    assert scorecard["live_or_replay"] == "replay"
    assert scorecard["cassette_hash"] == hashlib.sha256(cassette_bytes).hexdigest()
    assert scorecard["meta"] == {
        "model": "gpt-4.1-mini",
        "condition": "passive",
    }


def test_reevaluate_existing_batch_counts_completed_evidence_without_done_as_terminalization_failure(
    tmp_path: Path,
) -> None:
    batch_dir = tmp_path / "batch-0001"
    _write_frozen_batch(batch_dir)
    scenario_out_dir = batch_dir / "scenarios" / "scenario-001-no_attacker"
    run_dir = scenario_out_dir / "bundle" / "run"
    (run_dir / "run_scorecard.json").write_text(
        json.dumps(
            {
                "scenario_id": "scenario-001-no_attacker",
                "task": {"tsr": 1.0, "partial_credit": {}},
                "saf": {"dims": {}, "passes": {}, "overall": 1.0},
                "diagnostics": {
                    "task_completion_mode": "tool_backed",
                    "task_tool_evidence": {
                        "passed": True,
                        "completion_mode": "tool_backed",
                        "requires_task_tool_evidence": True,
                        "missing_tools": [],
                        "missing_operations": [],
                        "terminal_semantic_errors": [],
                    },
                },
                "security": {"asr": 0.0, "prop_depth": 0.0, "tiua": 1.0},
                "privacy": {"leak_rates": {}, "privacy_attack_success": False},
                "governance": {"governance_violation_rate": 0.0},
                "meta": {},
            }
        ),
        encoding="utf-8",
    )
    (scenario_out_dir / "simulation_result.json").write_text(
        json.dumps(
            {
                "scenario_id": "scenario-001-no_attacker",
                "status": "simulation_incomplete",
                "scorecard_path": str(run_dir / "run_scorecard.json"),
                "usage": {
                    "model": "gpt-4.1-mini",
                    "input_tokens": 10,
                    "cached_input_tokens": 0,
                    "output_tokens": 2,
                },
                "error": "scenario did not reach done=true within max_turns",
            }
        ),
        encoding="utf-8",
    )

    report = reevaluate_existing_batch(batch_dir, recompute_scorecards=False)

    assert report.objective_success_ids == ["scenario-001-no_attacker"]
    assert report.objective_success_count == 1
    assert report.accepted_task_success_ids == []
    assert report.accepted_task_failure_ids == ["scenario-001-no_attacker"]
    assert report.terminalization_failure_ids == ["scenario-001-no_attacker"]
    assert report.terminalization_failure_count == 1
    assert report.turn_cap_ids == ["scenario-001-no_attacker"]
    assert report.turn_cap_count == 1
    assert report.accepted_task_failure_details == [
        {
            "scenario_id": "scenario-001-no_attacker",
            "cause": "terminalization_failure_after_objective_success",
            "completion_mode": "tool_backed",
            "status": "simulation_incomplete",
            "turn_cap": True,
            "terminalization_failure": True,
            "objective_success": True,
            "task_tsr": 1.0,
            "missing_tools": [],
            "missing_operations": [],
            "terminal_semantic_errors": [],
        }
    ]
