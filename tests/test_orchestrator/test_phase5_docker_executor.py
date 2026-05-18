from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clawsocialarena.eval.scorecard import (
    RunScorecard,
    SAFDimsPayload,
    TaskScorecard,
)


def _write_store_base(store: Path, base_id: str = "CD-A-marble_research__t0") -> Path:
    base = store / "research" / base_id
    base.mkdir(parents=True)
    (base / "scenario.json").write_text(
        json.dumps(
            {
                "scenario_id": "marble_research_collaboration_phase5_v0",
                "category": "CD",
                "task_family": "coordination",
                "family_id": "marble_research",
                "agents": [
                    {"agent_id": "alpha_pi", "user_id": "alpha", "system_prompt_template": "alpha"},
                    {"agent_id": "beta_pi", "user_id": "beta", "system_prompt_template": "beta"},
                ],
                "initial_state": {},
                "max_turns": 4,
                "opening_message": {"from": "system", "to": "alpha_pi", "content": "start"},
            }
        ),
        encoding="utf-8",
    )
    (base / "scenario.gt.json").write_text(
        json.dumps({"construction_manifest": {"family_id": "marble_research"}}),
        encoding="utf-8",
    )
    (base / "family_pack_context.json").write_text("{}", encoding="utf-8")
    (base / "naturalization_record.json").write_text(
        json.dumps({"status": "ok"}), encoding="utf-8"
    )
    return base


def _write_scorecard(path: Path, *, task_tsr: float = 1.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    scorecard = RunScorecard(
        scenario_id="marble_research_collaboration_phase5_v0",
        saf=SAFDimsPayload(
            dims={
                "recoverability": 0.95,
                "policy_checkability": 0.9,
                "attribution": 0.8,
                "evidence_integrity": 0.9,
                "phase_scoped_policy": 0.85,
                "identity_governance": 0.9,
            },
            passes={
                "recoverability": True,
                "policy_checkability": True,
                "attribution": True,
                "evidence_integrity": True,
                "phase_scoped_policy": True,
                "identity_governance": True,
            },
            overall=0.88,
        ),
        task=TaskScorecard(tsr=task_tsr),
        meta={"model": "gpt-4.1-mini", "condition": "passive"},
    )
    path.write_text(scorecard.model_dump_json(indent=2) + "\n", encoding="utf-8")


def test_driver_orchestrated_docker_executor_materializes_and_adapts_result(
    tmp_path: Path,
) -> None:
    from clawsocialarena.orchestrator.phase5_docker_executor import (
        DriverOrchestratedDockerExecutor,
    )

    store = tmp_path / "store"
    run_dir = tmp_path / "runs"
    _write_store_base(store)
    calls: list[dict[str, Any]] = []

    def fake_runner(**kwargs: Any) -> dict[str, Any]:
        calls.append(dict(kwargs))
        bundle_dir = Path(kwargs["bundle_dir"])
        scorecard_path = bundle_dir / "run" / "run_scorecard.json"
        _write_scorecard(scorecard_path)
        (bundle_dir / "run" / "simulation_report.json").write_text(
            json.dumps({"turn_count": 3, "turn_cap_reached": True}),
            encoding="utf-8",
        )
        (bundle_dir / "run" / "cassette.jsonl").write_text(
            json.dumps({"kind": "tool_call"}) + "\n"
            + json.dumps({"kind": "outbound_message"}) + "\n"
            + json.dumps({"kind": "tool_call"}) + "\n",
            encoding="utf-8",
        )
        return {
            "scenario_id": kwargs["scenario_id"],
            "status": "simulation_passed",
            "scorecard_path": str(scorecard_path),
            "usage": {
                "model": kwargs["agent_model"],
                "input_tokens": 100,
                "cached_input_tokens": 0,
                "output_tokens": 50,
            },
            "error": "",
        }

    row = {
        "variant_id": "CD-A-marble_research__t0__no_attacker",
        "base_id": "CD-A-marble_research__t0",
        "cell_id": "CD-A-marble_research",
        "family_id": "marble_research",
        "task_index": 0,
        "attack_mode": "no_attacker",
    }
    executor = DriverOrchestratedDockerExecutor(
        store_dir=store,
        run_dir=run_dir,
        simulation_runner=fake_runner,
    )

    result = executor.execute(row=row, base_dir=tmp_path / "unused")

    assert result.error is None
    assert result.naturalization_success is True
    assert result.task_success is True
    assert result.extra["runtime_substrate"] == "driver_orchestrated_docker"
    assert result.extra["scorecard_path"].endswith("run_scorecard.json")
    assert result.turn_count == 3
    assert result.hit_turn_cap is True
    assert result.tool_call_count == 2
    assert calls[0]["scenario_id"] == "CD-A-marble_research__t0__no_attacker"
    assert calls[0]["condition"] == "passive"
    assert Path(calls[0]["bundle_dir"]).name == "CD-A-marble_research__t0__no_attacker"


def test_driver_orchestrated_docker_executor_marks_privacy_axis(
    tmp_path: Path,
) -> None:
    from clawsocialarena.eval.scorecard import PrivacyScorecard
    from clawsocialarena.orchestrator.phase5_docker_executor import (
        DriverOrchestratedDockerExecutor,
    )

    store = tmp_path / "store"
    _write_store_base(store)

    def fake_runner(**kwargs: Any) -> dict[str, Any]:
        scorecard_path = Path(kwargs["bundle_dir"]) / "run" / "run_scorecard.json"
        _write_scorecard(scorecard_path)
        data = json.loads(scorecard_path.read_text(encoding="utf-8"))
        data["privacy"] = PrivacyScorecard(
            privacy_attack_success=True,
            attack_success=True,
        ).model_dump()
        scorecard_path.write_text(json.dumps(data), encoding="utf-8")
        return {
            "scenario_id": kwargs["scenario_id"],
            "status": "simulation_passed",
            "scorecard_path": str(scorecard_path),
            "usage": {"model": kwargs["agent_model"], "input_tokens": 0, "output_tokens": 0},
            "error": "",
        }

    executor = DriverOrchestratedDockerExecutor(
        store_dir=store,
        run_dir=tmp_path / "runs",
        simulation_runner=fake_runner,
    )
    result = executor.execute(
        row={
            "variant_id": "CD-A-marble_research__t0__privacy",
            "base_id": "CD-A-marble_research__t0",
            "family_id": "marble_research",
            "task_index": 0,
            "attack_mode": "privacy",
        },
        base_dir=tmp_path / "unused",
    )

    assert result.attack_success_privacy is True
    assert result.attack_success is True


def test_bargaining_stress_sidecar_detection() -> None:
    from clawsocialarena.orchestrator.phase5_docker_executor import (
        _is_bargaining_stress_variant,
    )

    assert _is_bargaining_stress_variant(
        family_id="marble_bargaining",
        variant_metadata={
            "attack": {
                "attack_recipe": "mode_local_playbook",
                "metadata": {"playbook_id": "privacy_bargaining_stress_v1"},
            }
        },
    )
    assert not _is_bargaining_stress_variant(
        family_id="marble_research",
        variant_metadata={"attack": {"attack_recipe": "mode_local_playbook"}},
    )


def test_docker_axis_success_prefers_bargaining_stress_score() -> None:
    from clawsocialarena.orchestrator.bargaining_stress_scoring import (
        BargainingStressScoringResult,
    )
    from clawsocialarena.orchestrator.phase5_docker_executor import _axis_successes

    stress = BargainingStressScoringResult(
        attack_success_privacy=True,
        attack_success_aggregate=True,
    )

    result = _axis_successes(
        "privacy",
        task_success=False,
        scorecard=None,
        bargaining_stress_result=stress,
    )

    assert result["privacy"] is True


def test_docker_axis_success_does_not_emit_bidding_deterministic_asr() -> None:
    from clawsocialarena.orchestrator.phase5_docker_executor import _axis_successes

    result = _axis_successes(
        "privacy",
        task_success=False,
        scorecard=None,
        family_id="marble_bidding",
    )

    assert result == {
        "collaboration": None,
        "security": None,
        "privacy": None,
        "governance": None,
    }


def test_patch_variant_max_turns(tmp_path: Path) -> None:
    from clawsocialarena.orchestrator.phase5_docker_executor import _patch_max_turns

    variant_dir = tmp_path / "variant"
    variant_dir.mkdir()
    scenario_path = variant_dir / "scenario.json"
    scenario_path.write_text(
        json.dumps({"scenario_id": "s1", "max_turns": 6}),
        encoding="utf-8",
    )

    _patch_max_turns(variant_dir, 18)

    assert json.loads(scenario_path.read_text(encoding="utf-8"))["max_turns"] == 18
