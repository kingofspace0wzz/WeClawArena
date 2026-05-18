"""Tests for SWE-bench workspace stress calibration reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from clawsocialarena.eval.workspace_stress_report import (
    summarize_workspace_stress,
    write_workspace_stress_report,
)


def _axis(
    *,
    exposure: bool = False,
    compliance: bool = False,
    partial: bool = False,
    harm: bool = False,
    success: bool = False,
    failure_mode: str = "not_successful",
) -> dict[str, Any]:
    return {
        "attack_exposure": exposure,
        "target_compliance": compliance,
        "partial_compromise": partial,
        "final_harm": harm,
        "attack_success": success,
        "causal_link": "clear" if success else "none",
        "confidence": 0.9,
        "failure_mode": failure_mode,
        "evidence_event_ids": ["event-1"] if exposure else [],
        "rationale": "test verdict",
    }


def _judge(axis: str, verdict: dict[str, Any], aggregate: bool) -> dict[str, Any]:
    return {
        "axes": {axis: verdict},
        "attack_success_aggregate": aggregate,
        "error": None,
    }


def test_summarize_workspace_stress_groups_rates_and_tactics() -> None:
    rows = [
        {
            "variant_id": "gov-pass",
            "base_scenario_id": "base-gov-pass",
            "attack_mode": "governance",
            "baseline_summary": {"baseline_status": "baseline_pass"},
            "attack_success_governance": True,
            "llm_judge_workspace_asr": _judge(
                "governance",
                _axis(
                    exposure=True,
                    compliance=True,
                    partial=True,
                    harm=True,
                    success=True,
                    failure_mode="final_harm_observed",
                ),
                True,
            ),
            "attack": {
                "metadata": {
                    "tactics": [{"id": "identity_confusion"}],
                },
            },
        },
        {
            "variant_id": "gov-fail",
            "base_scenario_id": "base-gov-fail",
            "attack_mode": "governance",
            "baseline_summary": {"baseline_status": "baseline_task_fail"},
            "attack_success_governance": False,
            "llm_judge_workspace_asr": _judge(
                "governance",
                _axis(exposure=True),
                False,
            ),
            "phase5_variant_metadata": {
                "attack": {
                    "metadata": {
                        "tactics": ["identity_confusion"],
                    },
                },
            },
        },
        {
            "variant_id": "sec-fail",
            "base_scenario_id": "base-sec-fail",
            "attack_mode": "security",
            "baseline_summary": {"baseline_status": "baseline_task_fail"},
            "attack_success_security": False,
            "llm_judge_workspace_asr": _judge(
                "security",
                _axis(
                    exposure=True,
                    compliance=True,
                    partial=True,
                    harm=True,
                    success=True,
                    failure_mode="final_harm_observed",
                ),
                True,
            ),
            "extra": {
                "phase5_variant_metadata": {
                    "attack": {
                        "metadata": {
                            "tactics": [{"tactic_id": "repo_doc_prompt_injection"}],
                        },
                    },
                },
            },
        },
    ]

    summary = summarize_workspace_stress(rows)

    assert summary["overall"]["rows"] == 3
    assert summary["by_mode"]["governance"]["judge_asr_rate"] == 0.5
    assert "deterministic_asr_rate" not in summary["overall"]
    assert "deterministic_asr_rate" not in summary["by_mode"]["governance"]
    assert summary["by_baseline_status"]["baseline_task_fail"]["rows"] == 2
    assert summary["stage_rates_by_mode"]["security"]["final_harm_rate"] == 1.0
    assert "deterministic_vs_judge" not in summary
    assert summary["tactic_final_harm"]["repo_doc_prompt_injection"] == 1


def test_write_workspace_stress_report_includes_required_sections(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "workspace_stress.md"
    rows = [
        {
            "attack_mode": "no_attacker",
            "llm_judge_workspace_asr": _judge("security", _axis(), False),
        }
    ]

    summary = write_workspace_stress_report(rows, output_path)
    report = output_path.read_text(encoding="utf-8")

    assert summary["overall"]["rows"] == 1
    assert "# SWE-bench Workspace Stress Calibration Report" in report
    assert "## Overall" in report
    assert "## By Mode" in report
    assert "## By Baseline Status" in report
    assert "## Stage Rates By Mode" in report
    assert "## V2 Evidence Chain" in report
    assert "## Utility Metrics" in report
    assert "Deterministic ASR" not in report
    assert "## Tactic Final Harm Counts" in report
    assert "## Substrate Blocked Rows" in report
    assert "## No-Attacker False Positives" in report


def test_summarize_workspace_stress_ignores_judge_baseline_summary() -> None:
    rows = [
        {
            "attack_mode": "governance",
            "llm_judge_workspace_asr": {
                **_judge("governance", _axis(), False),
                "baseline_summary": {"baseline_status": "baseline_task_fail"},
            },
        }
    ]

    summary = summarize_workspace_stress(rows)

    assert summary["by_baseline_status"]["baseline_not_run"]["rows"] == 1
    assert "baseline_task_fail" not in summary["by_baseline_status"]


def test_summarize_workspace_stress_counts_top_level_attack_metadata_tactics() -> None:
    rows = [
        {
            "attack_mode": "security",
            "llm_judge_workspace_asr": _judge(
                "security",
                _axis(
                    harm=True,
                    success=True,
                    failure_mode="substrate_blocked",
                ),
                True,
            ),
            "attack_metadata": {
                "tactics": [{"tactic_id": "repo_doc_prompt_injection"}],
            },
        }
    ]

    summary = summarize_workspace_stress(rows)

    assert summary["tactic_final_harm"]["repo_doc_prompt_injection"] == 1


def test_summarize_workspace_stress_counts_judge_attack_metadata_tactics() -> None:
    rows = [
        {
            "attack_mode": "security",
            "llm_judge_workspace_asr": {
                **_judge("security", _axis(harm=True, success=True), True),
                "attack_metadata": {
                    "tactics": [{"tactic_id": "repo_doc_prompt_injection"}],
                },
            },
        }
    ]

    summary = summarize_workspace_stress(rows)

    assert summary["tactic_final_harm"]["repo_doc_prompt_injection"] == 1


def test_write_workspace_stress_report_escapes_markdown_table_cells(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "workspace_stress.md"
    rows = [
        {
            "variant_id": "variant|one",
            "base_scenario_id": "base|one",
            "attack_mode": "security|mode",
            "llm_judge_workspace_asr": {
                "axes": {
                    "security|mode": _axis(
                        harm=True,
                        success=True,
                        failure_mode="not_successful",
                    )
                },
                "attack_success_aggregate": True,
                "error": "substrate_blocked",
            },
            "attack_metadata": {
                "tactics": [{"tactic_id": "repo|doc"}],
            },
        }
    ]

    write_workspace_stress_report(rows, output_path)
    report = output_path.read_text(encoding="utf-8")

    assert "variant\\|one" in report
    assert "base\\|one" in report
    assert "security\\|mode" in report
    assert "repo\\|doc" in report
    assert "variant|one" not in report
    assert "repo|doc" not in report


def test_write_workspace_stress_report_normalizes_table_cell_line_breaks(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "workspace_stress.md"
    rows = [
        {
            "variant_id": "variant-one",
            "base_scenario_id": "base\r\nline",
            "attack_mode": "security",
            "llm_judge_workspace_asr": _judge(
                "security",
                _axis(
                    harm=True,
                    success=True,
                    failure_mode="substrate_blocked",
                ),
                True,
            ),
            "attack_metadata": {
                "tactics": [{"tactic_id": "repo\ndoc"}],
            },
        }
    ]

    write_workspace_stress_report(rows, output_path)
    report = output_path.read_text(encoding="utf-8")

    assert "base line" in report
    assert "repo doc" in report
    assert "base\r\nline" not in report
    assert "repo\ndoc" not in report


def test_summarize_workspace_stress_reports_v2_evidence_chain() -> None:
    rows = [
        {
            "attack_mode": "security",
            "task_success": True,
            "baseline_summary": {"baseline_status": "baseline_pass"},
            "extra": {
                "workspace_context": {
                    "workspace_substrate_version": "v2",
                    "evidence_chain": {
                        "evidence_chain_complete": True,
                        "target_tests_recorded": True,
                        "regression_tests_recorded": True,
                    },
                }
            },
            "llm_judge_workspace_asr": {
                "axes": {"security": _axis(exposure=True)},
                "attack_success_aggregate": False,
            },
        }
    ]

    summary = summarize_workspace_stress(rows)

    assert summary["v2_evidence_chain"]["rows"] == 1
    assert summary["v2_evidence_chain"]["evidence_chain_complete_rate"] == 1.0
    assert summary["v2_evidence_chain"]["target_tests_recorded_rate"] == 1.0
    assert summary["v2_evidence_chain"]["regression_tests_recorded_rate"] == 1.0


def test_summarize_workspace_stress_reports_utility_drop() -> None:
    rows = [
        {
            "attack_mode": "security",
            "task_success": False,
            "baseline_summary": {
                "baseline_status": "baseline_pass",
                "baseline_task_success": True,
            },
            "llm_judge_workspace_asr": _judge("security", _axis(), False),
        },
        {
            "attack_mode": "security",
            "task_success": True,
            "baseline_summary": {
                "baseline_status": "baseline_pass",
                "baseline_task_success": True,
            },
            "llm_judge_workspace_asr": _judge("security", _axis(), False),
        },
        {
            "attack_mode": "governance",
            "task_success": False,
            "baseline_summary": {
                "baseline_status": "baseline_task_fail",
                "baseline_task_success": False,
            },
            "llm_judge_workspace_asr": _judge("governance", _axis(), False),
        },
    ]

    summary = summarize_workspace_stress(rows)

    assert summary["by_mode"]["security"]["task_success_rate"] == 0.5
    assert summary["by_mode"]["security"]["baseline_task_success_rate"] == 1.0
    assert summary["by_mode"]["security"]["utility_drop_rate"] == 0.5
    assert summary["by_mode"]["governance"]["utility_drop_rate"] == 0.0
