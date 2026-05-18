from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clawsocialarena.orchestrator.phase5_executor import ScenarioResult


def _row(task: int, mode: str, family: str = "marble_bargaining") -> dict[str, Any]:
    base_id = f"CU-A-{family}__t{task}"
    return {
        "variant_id": f"{base_id}__{mode}",
        "base_id": base_id,
        "base_scenario_id": base_id,
        "bundle_dir": f"bargaining/{base_id}",
        "cell_id": f"CU-A-{family}",
        "family_id": family,
        "task_index": task,
        "tier_index": None,
        "attack_mode": mode,
    }


def test_select_bargaining_rows_uses_store_manifest_without_batch_assertions() -> None:
    from scripts.run_bargaining_stress_calibration import select_bargaining_rows

    rows = [
        _row(0, "no_attacker"),
        _row(0, "privacy"),
        _row(0, "security", family="marble_research"),
    ]

    selected = select_bargaining_rows({"rows": rows})

    assert [row["variant_id"] for row in selected] == [
        "CU-A-marble_bargaining__t0__no_attacker",
        "CU-A-marble_bargaining__t0__privacy",
    ]


def test_select_bargaining_rows_can_drop_baseline() -> None:
    from scripts.run_bargaining_stress_calibration import select_bargaining_rows

    rows = [_row(0, "no_attacker"), _row(0, "governance")]

    selected = select_bargaining_rows({"rows": rows}, include_baseline=False)

    assert [row["attack_mode"] for row in selected] == ["governance"]


def test_select_bargaining_rows_can_filter_modes() -> None:
    from scripts.run_bargaining_stress_calibration import select_bargaining_rows

    rows = [
        _row(0, "no_attacker"),
        _row(0, "governance"),
        _row(0, "security"),
        _row(0, "privacy"),
    ]

    selected = select_bargaining_rows(
        {"rows": rows},
        modes={"security", "governance"},
    )

    assert [row["attack_mode"] for row in selected] == ["governance", "security"]


def test_select_bargaining_rows_can_filter_base_ids() -> None:
    from scripts.run_bargaining_stress_calibration import select_bargaining_rows

    rows = [
        _row(0, "no_attacker"),
        _row(1, "no_attacker"),
        _row(1, "security"),
        _row(2, "no_attacker"),
    ]

    selected = select_bargaining_rows(
        {"rows": rows},
        base_ids={"CU-A-marble_bargaining__t1"},
    )

    assert [row["variant_id"] for row in selected] == [
        "CU-A-marble_bargaining__t1__no_attacker",
        "CU-A-marble_bargaining__t1__security",
    ]


def test_run_calibration_rows_writes_jsonl_and_summary(tmp_path: Path) -> None:
    from scripts.run_bargaining_stress_calibration import run_calibration_rows

    rows = [_row(0, "no_attacker"), _row(0, "privacy")]
    calls: list[str] = []

    class FakeExecutor:
        def execute(self, *, row: dict[str, Any], base_dir: Path) -> ScenarioResult:
            calls.append(str(base_dir))
            mode = str(row["attack_mode"])
            return ScenarioResult(
                variant_id=str(row["variant_id"]),
                base_scenario_id=str(row["base_id"]),
                cell_id=str(row["cell_id"]),
                family_id=str(row["family_id"]),
                task_index=int(row["task_index"]),
                tier_index=None,
                attack_mode=mode,
                attack_recipe="mode_local_playbook" if mode != "no_attacker" else None,
                naturalization_success=True,
                task_success=mode == "no_attacker",
                attack_success_privacy=True if mode == "privacy" else None,
                attack_success=True if mode == "privacy" else None,
                turn_count=7,
            )

    summary = run_calibration_rows(
        rows=rows,
        executor=FakeExecutor(),
        store_dir=tmp_path / "store",
        out_dir=tmp_path / "out",
    )

    results_path = tmp_path / "out" / "BARGAINING_STRESS_RESULTS.jsonl"
    summary_path = tmp_path / "out" / "BARGAINING_STRESS_REPORT.json"
    written = [json.loads(line) for line in results_path.read_text().splitlines()]

    assert calls == [str(tmp_path / "store"), str(tmp_path / "store")]
    assert len(written) == 2
    assert summary_path.is_file()
    assert summary["rows_total"] == 2
    assert summary["task_success_rate_baseline"] == 1.0
    assert summary["attack_success_rate_by_axis"]["privacy"] == 1.0


def test_summarize_results_uses_raw_tsr_denominator() -> None:
    from scripts.run_bargaining_stress_calibration import summarize_results

    rows = [_row(1, "no_attacker"), _row(2, "no_attacker"), _row(3, "no_attacker")]
    results = [
        ScenarioResult(
            variant_id=str(rows[0]["variant_id"]),
            base_scenario_id=str(rows[0]["base_id"]),
            cell_id=str(rows[0]["cell_id"]),
            family_id=str(rows[0]["family_id"]),
            task_index=1,
            tier_index=None,
            attack_mode="no_attacker",
            attack_recipe=None,
            naturalization_success=True,
            task_success=True,
            turn_count=11,
        ),
        ScenarioResult(
            variant_id=str(rows[1]["variant_id"]),
            base_scenario_id=str(rows[1]["base_id"]),
            cell_id=str(rows[1]["cell_id"]),
            family_id=str(rows[1]["family_id"]),
            task_index=2,
            tier_index=None,
            attack_mode="no_attacker",
            attack_recipe=None,
            naturalization_success=True,
            task_success=False,
            error="scenario did not reach done=true within max_turns",
            hit_turn_cap=True,
            turn_count=39,
        ),
        ScenarioResult(
            variant_id=str(rows[2]["variant_id"]),
            base_scenario_id=str(rows[2]["base_id"]),
            cell_id=str(rows[2]["cell_id"]),
            family_id=str(rows[2]["family_id"]),
            task_index=3,
            tier_index=None,
            attack_mode="no_attacker",
            attack_recipe=None,
            naturalization_success=True,
            task_success=None,
            error="unknown recipient_id from agent reply: 'owner_id'",
            turn_count=0,
        ),
    ]

    summary = summarize_results(rows=rows, results=results, elapsed_seconds=1.0)

    assert summary["task_success_rate_baseline"] == 1 / 3
    assert summary["rows_failed_before_scorecard"] == 1
    assert summary["rows_hit_turn_cap"] == 1
