from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from clawsocialarena.simulation.batch_runner import BatchReport


GateDecision = Literal["proceed", "re_score", "regenerate_rows", "stop_scale_out"]


class ReviewAgentFeedback(BaseModel):
    summary: str = ""
    scenario_realism_issues: list[str] = Field(default_factory=list)
    filesystem_database_realism_issues: list[str] = Field(default_factory=list)
    task_difficulty_issues: list[str] = Field(default_factory=list)
    simulation_trajectory_issues: list[str] = Field(default_factory=list)
    terminalization_issues: list[str] = Field(default_factory=list)
    attack_vector_quality_issues: list[str] = Field(default_factory=list)
    evaluation_only_issues: list[str] = Field(default_factory=list)
    rows_for_deeper_inspection: list[str] = Field(default_factory=list)
    rows_to_keep: list[str] = Field(default_factory=list)
    rows_to_rerun: list[str] = Field(default_factory=list)
    rows_to_regenerate: list[str] = Field(default_factory=list)
    evaluator_fixes_needed: list[str] = Field(default_factory=list)
    recommended_decision: GateDecision | None = None
    raw_markdown: str = ""


def render_qc_report(
    batch_report: BatchReport | dict[str, Any],
    *,
    feedback: ReviewAgentFeedback | None = None,
    gate_decision: GateDecision | None = None,
    next_batch_command: str | None = None,
) -> str:
    report = _normalize_batch_report(batch_report)
    feedback = feedback or ReviewAgentFeedback()
    decision = gate_decision or feedback.recommended_decision or _infer_gate_decision(
        report,
        feedback,
    )
    rows_to_regenerate = feedback.rows_to_regenerate or _deterministic_rows_to_regenerate(
        report,
        decision,
    )
    if feedback.rows_to_rerun:
        rerun_set = set(feedback.rows_to_rerun)
        rows_to_regenerate = [
            scenario_id
            for scenario_id in rows_to_regenerate
            if scenario_id not in rerun_set
        ]
    rows_to_keep = feedback.rows_to_keep or _deterministic_rows_to_keep(
        report,
        rows_to_regenerate,
    )
    scenario_count = len(report.scenario_ids)
    lines: list[str] = [
        f"# Construction QC Report: {report.batch_id}",
        "",
        "## Batch Summary",
        f"- Scenario count: {scenario_count}",
        f"- Accepted runs: {report.accepted_count} / {scenario_count}",
        _format_optional_line("Audit condition", report.condition),
        _format_counts("Condition distribution", report.condition_counts),
        f"- Readiness failures: {report.failed_count}",
        f"- Construction model: {report.usage.construction.model}",
        f"- Simulated-agent model: {report.usage.simulation.model}",
        (
            "- Construction tokens: "
            f"{report.usage.construction.input_tokens} input, "
            f"{report.usage.construction.cached_input_tokens} cached input, "
            f"{report.usage.construction.output_tokens} output"
        ),
        (
            "- Simulation tokens: "
            f"{report.usage.simulation.input_tokens} input, "
            f"{report.usage.simulation.cached_input_tokens} cached input, "
            f"{report.usage.simulation.output_tokens} output"
        ),
        (
            "- Observed cost: "
            f"${report.usage.total_estimated_cost_usd:.4f} total, "
            f"${report.usage.construction_estimated_cost_usd:.4f} construction, "
            f"${report.usage.simulation_estimated_cost_usd:.4f} simulation"
        ),
    ]
    if report.projected_full_benchmark_cost_usd is not None:
        lines.append(
            "- Projected 868-variant pilot cost: "
            f"${report.projected_full_benchmark_cost_usd.point_estimate:.2f} "
            "point estimate"
        )

    lines.extend(
        [
            "",
            "## Batch Composition",
            _format_optional_line(
                "Selection strategy",
                report.task_distribution.selection_strategy,
            ),
            _format_optional_line("Sweep index", report.task_distribution.sweep_index),
            (
                "- Base-task coverage: "
                f"{report.task_distribution.base_task_count} base tasks"
            ),
            _format_counts(
                "Category distribution",
                report.task_distribution.category_counts,
            ),
            _format_counts(
                "Task-family distribution",
                report.task_distribution.family_counts,
            ),
            _format_counts(
                "Designed-difficulty distribution",
                report.task_distribution.designed_difficulty_counts,
            ),
            _format_counts(
                "Attack-mode distribution",
                report.task_distribution.attack_mode_counts,
            ),
            _format_counts(
                "Attack-recipe distribution",
                report.attack_recipe_counts,
            ),
            _format_counts(
                "Attack-intensity distribution",
                report.attack_intensity_counts,
            ),
            "",
            "## Deterministic Metrics",
            (
                "- Task success: "
                f"{report.task_success_count} / {report.accepted_count} "
                f"({_format_percent(report.task_success_count, report.accepted_count)})"
            ),
            (
                "- Objective success: "
                f"{report.objective_success_count} / {report.accepted_count} "
                f"({_format_percent(report.objective_success_count, report.accepted_count)})"
            ),
            (
                "- Accepted task failures: "
                f"{report.accepted_task_failure_count}"
            ),
            f"- Terminalization failures: {report.terminalization_failure_count}",
            _format_counts(
                "Accepted task failure causes",
                report.accepted_task_failure_cause_counts,
            ),
            _format_attack_attempt_summary(report),
            _format_counts(
                "Attack-stage summary",
                report.attack_stage_summary,
            ),
            f"- Privacy attack successes: {report.privacy_attack_success_count}",
            f"- Security attack successes: {report.security_attack_success_count}",
            f"- Governance attack successes: {report.governance_attack_success_count}",
            (
                "- Seeded governance violations: "
                f"{report.seeded_governance_violation_count}"
            ),
            (
                "- Model-induced governance attack successes: "
                f"{report.model_induced_governance_attack_success_count}"
            ),
            f"- Resource/tool violations: {report.resource_tool_violation_count}",
            f"- Turn-cap outcomes: {report.turn_cap_count}",
            _format_saf_summary(report),
            (
                "- SAF applicable pass rate: "
                f"{_format_optional_percent(report.audit_summary.saf_applicable_pass_rate)}"
            ),
            (
                "- SAF applicability coverage: "
                f"{_format_optional_percent(report.audit_summary.saf_applicability_coverage)}"
            ),
            _format_counts(
                "SAF dimension means",
                report.audit_summary.saf_dim_means,
            ),
            _format_counts(
                "SAF dimension applicable counts",
                report.audit_summary.saf_dim_applicable_counts,
            ),
            _format_counts(
                "SAF dimension not-applicable counts",
                report.audit_summary.saf_dim_not_applicable_counts,
            ),
            _format_counts(
                "SAF dimension pass counts",
                report.audit_summary.saf_dim_pass_counts,
            ),
            _format_counts(
                "SAF dimension failure counts",
                report.audit_summary.saf_dim_failure_counts,
            ),
            "",
            "## Review-Agent Feedback",
        ]
    )
    lines.extend(_feedback_section(feedback))
    lines.extend(
        [
            "",
            "## Gate Decision",
            f"- Decision: {decision}",
            f"- Rows to keep: {_format_list(rows_to_keep)}",
            (
                "- Rows to rerun without regeneration: "
                f"{_format_list(feedback.rows_to_rerun)}"
            ),
            (
                "- Rows to regenerate or exclude: "
                f"{_format_list(rows_to_regenerate)}"
            ),
            (
                "- Evaluator fixes needed: "
                f"{_format_list(feedback.evaluator_fixes_needed)}"
            ),
            f"- Next batch command: {next_batch_command or 'Not specified.'}",
            "",
        ]
    )
    return "\n".join(lines)


def write_qc_report(
    *,
    batch_report_path: Path,
    review_feedback_path: Path | None = None,
    output_path: Path | None = None,
    gate_decision: GateDecision | None = None,
    next_batch_command: str | None = None,
) -> Path:
    report = BatchReport.model_validate_json(
        batch_report_path.read_text(encoding="utf-8")
    )
    feedback = load_review_agent_feedback(review_feedback_path)
    output_path = output_path or default_qc_report_path(batch_report_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        render_qc_report(
            report,
            feedback=feedback,
            gate_decision=gate_decision,
            next_batch_command=next_batch_command,
        ),
        encoding="utf-8",
    )
    return output_path


def load_review_agent_feedback(path: Path | None) -> ReviewAgentFeedback:
    if path is None:
        return ReviewAgentFeedback()
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return ReviewAgentFeedback.model_validate(json.loads(text))
    return ReviewAgentFeedback(raw_markdown=text.strip())


def default_qc_report_path(batch_report_path: Path) -> Path:
    batch_dir = batch_report_path.parent
    batch_id = batch_dir.name
    if batch_dir.parent.name == "batches":
        reviews_dir = batch_dir.parent.parent / "reviews"
    else:
        reviews_dir = batch_dir.parent / "reviews"
    return reviews_dir / f"{batch_id}-qc-report.md"


def _normalize_batch_report(batch_report: BatchReport | dict[str, Any]) -> BatchReport:
    if isinstance(batch_report, BatchReport):
        return batch_report
    return BatchReport.model_validate(batch_report)


def _infer_gate_decision(
    report: BatchReport,
    feedback: ReviewAgentFeedback,
) -> GateDecision:
    if (
        feedback.scenario_realism_issues
        or feedback.filesystem_database_realism_issues
        or feedback.task_difficulty_issues
        or feedback.simulation_trajectory_issues
        or feedback.attack_vector_quality_issues
        or feedback.rows_to_regenerate
    ):
        return "regenerate_rows"
    if feedback.evaluation_only_issues or feedback.evaluator_fixes_needed:
        return "re_score"
    if report.failed_count:
        return "stop_scale_out"
    return "proceed"


def _deterministic_rows_to_regenerate(
    report: BatchReport,
    decision: GateDecision,
) -> list[str]:
    if decision == "proceed":
        return []
    failed_ids = [
        str(scenario.get("scenario_id"))
        for scenario in report.failed_scenarios
        if scenario.get("scenario_id")
    ]
    if decision == "stop_scale_out":
        return _unique_in_order(failed_ids)
    if decision == "regenerate_rows":
        attack_success_ids = set(report.attack_success_ids)
        unexplained_task_failure_ids = [
            scenario_id
            for scenario_id in report.accepted_task_failure_ids
            if scenario_id not in attack_success_ids
        ]
        return _unique_in_order(
            [
                *unexplained_task_failure_ids,
                *failed_ids,
                *report.attack_unresolved_ids,
            ]
        )
    return []


def _deterministic_rows_to_keep(
    report: BatchReport,
    rows_to_regenerate: list[str],
) -> list[str]:
    regenerate_set = set(rows_to_regenerate)
    return [
        scenario_id
        for scenario_id in report.accepted_scenario_ids
        if scenario_id not in regenerate_set
    ]


def _unique_in_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _feedback_section(feedback: ReviewAgentFeedback) -> list[str]:
    lines: list[str] = []
    if feedback.summary:
        lines.append(f"- Summary: {feedback.summary}")
    lines.extend(_feedback_items("Scenario realism issues", feedback.scenario_realism_issues))
    lines.extend(
        _feedback_items(
            "Filesystem and database realism issues",
            feedback.filesystem_database_realism_issues,
        )
    )
    lines.extend(_feedback_items("Task difficulty issues", feedback.task_difficulty_issues))
    lines.extend(
        _feedback_items(
            "Simulation trajectory issues",
            feedback.simulation_trajectory_issues,
        )
    )
    lines.extend(
        _feedback_items(
            "Terminalization issues",
            feedback.terminalization_issues,
        )
    )
    lines.extend(
        _feedback_items(
            "Attack-vector quality issues",
            feedback.attack_vector_quality_issues,
        )
    )
    lines.extend(_feedback_items("Evaluation-only issues", feedback.evaluation_only_issues))
    lines.extend(
        _feedback_items(
            "Rows recommended for deeper inspection",
            feedback.rows_for_deeper_inspection,
        )
    )
    if feedback.raw_markdown:
        lines.extend(["", "### Raw Review-Agent Notes", feedback.raw_markdown])
    return lines


def _feedback_items(label: str, items: list[str]) -> list[str]:
    if not items:
        return [f"- {label}: none"]
    return [f"- {label}:"] + [f"- {item}" for item in items]


def _format_saf_summary(report: BatchReport) -> str:
    summary = report.audit_summary
    parts = [
        f"failures: {report.saf_failure_count}",
        f"scorecards: {summary.saf_scorecard_count}",
    ]
    if summary.saf_overall_min is not None:
        parts.append(f"overall min: {summary.saf_overall_min:.3f}")
    if summary.saf_pass_rate is not None:
        parts.append(f"pass rate: {summary.saf_pass_rate:.1%}")
    mean = (
        f"{summary.saf_overall_mean:.3f}"
        if summary.saf_overall_mean is not None
        else "n/a"
    )
    return f"- SAF overall mean: {mean}; {'; '.join(parts)}"


def _format_attack_attempt_summary(report: BatchReport) -> str:
    return (
        "- Attack attempts: "
        f"{report.attack_attempt_count}; successes: "
        f"{report.attack_success_count}; "
        f"{_attack_no_success_label(report)}: "
        f"{report.attack_resisted_count}; unresolved: "
        f"{report.attack_unresolved_count}"
    )


def _attack_no_success_label(report: BatchReport) -> str:
    conditions = _recorded_conditions(report)
    if not conditions:
        return "no success signal"
    if conditions == {"enforce"}:
        return "blocked or resisted"
    if conditions <= {"baseline", "passive"}:
        return "success not observed"
    return "no success signal"


def _recorded_conditions(report: BatchReport) -> set[str]:
    conditions = {condition for condition in report.condition_counts if condition}
    if report.condition:
        conditions.add(report.condition)
    return conditions


def _format_counts(label: str, counts: dict[str, Any]) -> str:
    if not counts:
        return f"- {label}: none"
    rendered = ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    return f"- {label}: {rendered}"


def _format_optional_line(label: str, value: Any) -> str:
    return f"- {label}: {value if value is not None else 'not recorded'}"


def _format_percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "n/a"
    return f"{numerator / denominator:.1%}"


def _format_optional_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1%}"


def _format_list(items: list[Any]) -> str:
    if not items:
        return "none"
    return ", ".join(str(item) for item in items)
