from __future__ import annotations

from pathlib import Path
from typing import Any

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.shadow_log import ShadowLog
from clawsocialarena.eval.runner import EvalRunner
from clawsocialarena.llm.costing import TokenUsage
from clawsocialarena.scenario.models import GTBundle
from clawsocialarena.simulation.batch_runner import (
    BatchReport,
    BatchScenarioInput,
    BatchTaskDistribution,
    BatchUsage,
    ScenarioScorecardDigest,
    build_batch_report,
    build_task_distribution,
    _append_scorecard_digest,
    _is_accepted_simulation,
    _load_existing_simulation_result,
    _normalize_attack_attempt_denominators,
    _normalize_collaboration_attribution_against_baseline,
    _read_json,
    _read_optional_json,
    _record_accepted_task_outcome,
    _scenario_scorecard_digest,
    _simulation_acceptance_error,
)


def reevaluate_existing_batch(
    batch_dir: Path,
    *,
    recompute_scorecards: bool = False,
    agent_model: str | None = None,
) -> BatchReport:
    """Rebuild a batch report from frozen batch artifacts.

    This path never calls the naturalizer, OpenAI APIs, Docker, or the live
    simulator. When ``recompute_scorecards`` is true, each scenario scorecard
    is rebuilt from the persisted action/shadow logs, cassette, GT bundle, and
    resource final state before the aggregate report is recomputed.
    """

    batch_dir = Path(batch_dir)
    existing_report = _read_existing_report(batch_dir)
    scenario_ids = _batch_scenario_ids(batch_dir, existing_report)
    if not scenario_ids:
        raise ValueError(f"no scenarios found in batch directory {batch_dir}")
    if recompute_scorecards:
        for scenario_id in scenario_ids:
            recompute_existing_run_scorecard(
                batch_dir / "scenarios" / scenario_id,
                agent_model=agent_model or _existing_agent_model(existing_report),
            )
    return _rebuild_batch_report(batch_dir, existing_report, scenario_ids)


def recompute_existing_run_scorecard(
    scenario_out_dir: Path,
    *,
    agent_model: str | None = None,
) -> Path:
    """Recompute ``bundle/run/run_scorecard.json`` from frozen run logs."""

    scenario_out_dir = Path(scenario_out_dir)
    bundle_dir = scenario_out_dir / "bundle"
    run_dir = bundle_dir / "run"
    gt_path = bundle_dir / "scenario.gt.json"
    action_log_path = run_dir / "action_log.db"
    shadow_log_path = run_dir / "action_log.shadow.db"
    cassette_path = run_dir / "cassette.jsonl"
    missing = [
        str(path)
        for path in (gt_path, action_log_path, shadow_log_path, cassette_path)
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError(
            "cannot recompute run scorecard; missing frozen artifacts: "
            + ", ".join(missing)
        )

    gt = GTBundle.model_validate(_read_json(gt_path))
    old_scorecard = _read_optional_json(run_dir / "run_scorecard.json")
    scorecard = EvalRunner().evaluate(
        action_log=ActionLog(action_log_path),
        shadow_log=ShadowLog(shadow_log_path),
        gt=gt,
        cassette_path=cassette_path,
        live_or_replay="replay",
        meta=_offline_evaluation_meta(old_scorecard, agent_model=agent_model),
        resource_root=(bundle_dir / "resources")
        if (bundle_dir / "resources").exists()
        else None,
    )
    scorecard_path = run_dir / "run_scorecard.json"
    scorecard_path.write_text(
        scorecard.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return scorecard_path


def _rebuild_batch_report(
    batch_dir: Path,
    existing_report: dict[str, Any],
    scenario_ids: list[str],
) -> BatchReport:
    accepted_scenario_ids: list[str] = []
    accepted_task_success_ids: list[str] = []
    accepted_task_failure_ids: list[str] = []
    accepted_task_failure_details: list[dict[str, Any]] = []
    attack_success_ids: list[str] = []
    attack_resisted_ids: list[str] = []
    attack_unresolved_ids: list[str] = []
    attack_attempt_ids: list[str] = []
    resource_tool_violation_ids: list[str] = []
    attack_classification_details: list[dict[str, Any]] = []
    collaboration_attack_success_ids: list[str] = []
    privacy_attack_success_ids: list[str] = []
    security_attack_success_ids: list[str] = []
    governance_attack_success_ids: list[str] = []
    seeded_governance_violation_ids: list[str] = []
    model_induced_governance_attack_success_ids: list[str] = []
    saf_failure_ids: list[str] = []
    turn_cap_ids: list[str] = []
    turn_cap_task_failure_ids: list[str] = []
    scenario_scorecard_digests: list[ScenarioScorecardDigest] = []
    failed_scenarios: list[dict[str, Any]] = []

    for scenario_id in scenario_ids:
        scenario_out_dir = batch_dir / "scenarios" / scenario_id
        simulation = _load_existing_simulation_result(scenario_out_dir)
        if _is_accepted_simulation(simulation, scenario_id, scenario_out_dir):
            accepted_scenario_ids.append(scenario_id)
            _record_accepted_task_outcome(
                scenario_id=scenario_id,
                scenario_out_dir=scenario_out_dir,
                accepted_task_success_ids=accepted_task_success_ids,
                accepted_task_failure_ids=accepted_task_failure_ids,
                accepted_task_failure_details=accepted_task_failure_details,
                attack_success_ids=attack_success_ids,
                attack_resisted_ids=attack_resisted_ids,
                attack_unresolved_ids=attack_unresolved_ids,
                attack_attempt_ids=attack_attempt_ids,
                resource_tool_violation_ids=resource_tool_violation_ids,
                attack_classification_details=attack_classification_details,
                collaboration_attack_success_ids=collaboration_attack_success_ids,
                privacy_attack_success_ids=privacy_attack_success_ids,
                security_attack_success_ids=security_attack_success_ids,
                governance_attack_success_ids=governance_attack_success_ids,
                seeded_governance_violation_ids=seeded_governance_violation_ids,
                model_induced_governance_attack_success_ids=(
                    model_induced_governance_attack_success_ids
                ),
                saf_failure_ids=saf_failure_ids,
                turn_cap_ids=turn_cap_ids,
                turn_cap_task_failure_ids=turn_cap_task_failure_ids,
                scenario_scorecard_digests=scenario_scorecard_digests,
            )
            continue
        failed_scenarios.append(
            {
                "scenario_id": scenario_id,
                "status": simulation.status if simulation is not None else "missing",
                "error": _simulation_acceptance_error(
                    simulation,
                    scenario_id,
                    scenario_out_dir,
                ),
            }
        )
        scorecard = _read_optional_json(
            scenario_out_dir / "bundle" / "run" / "run_scorecard.json"
        )
        if isinstance(scorecard, dict):
            _append_scorecard_digest(
                scenario_scorecard_digests,
                _scenario_scorecard_digest(
                    scenario_id=scenario_id,
                    scenario_out_dir=scenario_out_dir,
                    scorecard=scorecard,
                ),
            )

    non_attributable_collaboration_ids = (
        _normalize_collaboration_attribution_against_baseline(
            accepted_task_failure_ids=accepted_task_failure_ids,
            attack_success_ids=attack_success_ids,
            attack_resisted_ids=attack_resisted_ids,
            attack_unresolved_ids=attack_unresolved_ids,
            collaboration_attack_success_ids=collaboration_attack_success_ids,
            attack_classification_details=attack_classification_details,
        )
    )
    if non_attributable_collaboration_ids:
        # Keep parity with live batch reporting. This only annotates scorecards
        # that are already known to be non-attributable collaboration failures.
        from clawsocialarena.simulation.batch_runner import (
            _mark_non_attributable_collaboration_scorecards,
        )

        _mark_non_attributable_collaboration_scorecards(
            out_dir=batch_dir,
            scenario_ids=non_attributable_collaboration_ids,
        )
    _normalize_attack_attempt_denominators(
        attack_attempt_ids=attack_attempt_ids,
        attack_classification_details=attack_classification_details,
    )

    return build_batch_report(
        batch_id=str(existing_report.get("batch_id") or batch_dir.name),
        scenario_ids=scenario_ids,
        accepted_scenario_ids=accepted_scenario_ids,
        failed_scenarios=failed_scenarios,
        usage=_existing_usage(existing_report),
        stop_for_review=True,
        condition=_existing_condition(existing_report),
        base_task_ids=_existing_base_task_ids(batch_dir, existing_report, scenario_ids),
        construction_unit=str(
            existing_report.get("construction_unit") or "scenario_variant"
        ),
        accepted_task_success_ids=accepted_task_success_ids,
        accepted_task_failure_ids=accepted_task_failure_ids,
        accepted_task_failure_details=accepted_task_failure_details,
        attack_success_ids=attack_success_ids,
        attack_resisted_ids=attack_resisted_ids,
        attack_unresolved_ids=attack_unresolved_ids,
        attack_attempt_ids=attack_attempt_ids,
        resource_tool_violation_ids=resource_tool_violation_ids,
        attack_classification_details=attack_classification_details,
        collaboration_attack_success_ids=collaboration_attack_success_ids,
        privacy_attack_success_ids=privacy_attack_success_ids,
        security_attack_success_ids=security_attack_success_ids,
        governance_attack_success_ids=governance_attack_success_ids,
        seeded_governance_violation_ids=seeded_governance_violation_ids,
        model_induced_governance_attack_success_ids=(
            model_induced_governance_attack_success_ids
        ),
        saf_failure_ids=saf_failure_ids,
        turn_cap_ids=turn_cap_ids,
        turn_cap_task_failure_ids=turn_cap_task_failure_ids,
        scenario_scorecard_digests=scenario_scorecard_digests,
        task_distribution=_existing_task_distribution(batch_dir, scenario_ids),
    )


def _existing_condition(existing_report: dict[str, Any]) -> str | None:
    condition = existing_report.get("condition")
    return condition if isinstance(condition, str) and condition else None


def _offline_evaluation_meta(
    old_scorecard: Any,
    *,
    agent_model: str | None,
) -> dict[str, Any]:
    old_meta = old_scorecard.get("meta") if isinstance(old_scorecard, dict) else {}
    old_meta = old_meta if isinstance(old_meta, dict) else {}
    meta: dict[str, Any] = {
        "model": agent_model or str(old_meta.get("model") or ""),
        "condition": str(old_meta.get("condition") or "passive"),
    }
    terminal_reason = old_meta.get("terminal_task_failure_reason")
    if isinstance(terminal_reason, str) and terminal_reason:
        if "caused accepted task failure:" not in terminal_reason and not terminal_reason.startswith(
            "baseline no_attacker task failed"
        ):
            meta["terminal_task_failure_reason"] = terminal_reason
    return {key: value for key, value in meta.items() if value}


def _read_existing_report(batch_dir: Path) -> dict[str, Any]:
    report = _read_optional_json(batch_dir / "batch_report.json")
    return report if isinstance(report, dict) else {}


def _batch_scenario_ids(
    batch_dir: Path,
    existing_report: dict[str, Any],
) -> list[str]:
    selection = _read_optional_json(batch_dir / "batch_selection.json")
    if isinstance(selection, dict):
        scenario_ids = selection.get("scenario_ids")
        if isinstance(scenario_ids, list):
            return [str(item) for item in scenario_ids if isinstance(item, str)]
    scenario_ids = existing_report.get("scenario_ids")
    if isinstance(scenario_ids, list):
        return [str(item) for item in scenario_ids if isinstance(item, str)]
    scenarios_dir = batch_dir / "scenarios"
    if not scenarios_dir.exists():
        return []
    return sorted(path.name for path in scenarios_dir.iterdir() if path.is_dir())


def _existing_usage(existing_report: dict[str, Any]) -> BatchUsage:
    usage = existing_report.get("usage")
    if isinstance(usage, dict):
        return BatchUsage.model_validate(usage)
    return BatchUsage(
        construction=TokenUsage(model=""),
        simulation=TokenUsage(model=""),
    )


def _existing_agent_model(existing_report: dict[str, Any]) -> str | None:
    usage = existing_report.get("usage")
    if not isinstance(usage, dict):
        return None
    simulation = usage.get("simulation")
    if not isinstance(simulation, dict):
        return None
    model = simulation.get("model")
    return model if isinstance(model, str) and model else None


def _existing_base_task_ids(
    batch_dir: Path,
    existing_report: dict[str, Any],
    scenario_ids: list[str],
) -> list[str]:
    selection = _read_optional_json(batch_dir / "batch_selection.json")
    for source in (existing_report, selection):
        if isinstance(source, dict):
            base_task_ids = source.get("base_task_ids")
            if isinstance(base_task_ids, list):
                return [str(item) for item in base_task_ids if isinstance(item, str)]
    return list(dict.fromkeys(_base_task_id_from_skeleton(batch_dir, sid) for sid in scenario_ids))


def _base_task_id_from_skeleton(batch_dir: Path, scenario_id: str) -> str:
    payload = _read_optional_json(
        batch_dir / "scenarios" / scenario_id / "skeleton_payload.json"
    )
    if isinstance(payload, dict):
        row = payload.get("index_row")
        if isinstance(row, dict):
            base_task_id = row.get("base_task_id")
            if isinstance(base_task_id, str) and base_task_id:
                return base_task_id
    return scenario_id


def _existing_task_distribution(
    batch_dir: Path,
    scenario_ids: list[str],
) -> BatchTaskDistribution:
    selection = _read_optional_json(batch_dir / "batch_selection.json")
    if isinstance(selection, dict):
        raw = selection.get("task_distribution")
        if isinstance(raw, dict):
            return BatchTaskDistribution.model_validate(raw)
    inputs: list[BatchScenarioInput] = []
    for scenario_id in scenario_ids:
        payload = _read_optional_json(
            batch_dir / "scenarios" / scenario_id / "skeleton_payload.json"
        )
        inputs.append(
            BatchScenarioInput(
                scenario_id=scenario_id,
                bundle_dir=batch_dir / "scenarios" / scenario_id / "bundle",
                skeleton_payload=payload if isinstance(payload, dict) else {},
            )
        )
    return build_task_distribution(inputs)
