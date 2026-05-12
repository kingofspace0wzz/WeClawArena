from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from clawsocialarena.llm.costing import TokenUsage
from clawsocialarena.simulation.batch_runner import (
    BatchReport,
    BatchScenarioInput,
    BatchTaskDistribution,
    BatchUsage,
    ScenarioScorecardDigest,
    SimulationRunner,
    build_batch_report,
    build_task_distribution,
    run_simulation_for_bundle,
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
from clawsocialarena.types import AuditCondition


def run_condition_sentinel_batch(
    *,
    source_batch_dir: Path,
    batch_id: str,
    out_dir: Path,
    scenario_ids: list[str] | None = None,
    conditions: list[str | AuditCondition] | None = None,
    limit: int = 5,
    agent_model: str | None = None,
    construction_model: str | None = None,
    simulation_runner: SimulationRunner | None = None,
    rerun_existing: bool = False,
) -> BatchReport:
    """Rerun accepted naturalized bundles under selected audit conditions.

    The sentinel batch is a runtime-only gate. It copies bundles from an
    existing construction batch, reruns simulations under condition variants,
    and writes a normal batch report without invoking naturalization.
    """

    source_batch_dir = Path(source_batch_dir)
    batch_dir = Path(out_dir) / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    source_report = _source_batch_report(source_batch_dir)
    source_ids = _selected_source_scenario_ids(
        source_report=source_report,
        explicit_ids=scenario_ids,
        limit=limit,
    )
    condition_values = _condition_values(conditions)
    agent_model = agent_model or _source_model(source_report, usage_key="simulation")
    construction_model = construction_model or _source_model(
        source_report,
        usage_key="construction",
    )

    sentinel_inputs: list[BatchScenarioInput] = []
    scenario_pairs: list[dict[str, str]] = []
    for source_id in source_ids:
        source_scenario_dir = source_batch_dir / "scenarios" / source_id
        if not source_scenario_dir.exists():
            raise FileNotFoundError(f"missing source scenario directory: {source_id}")
        for condition in condition_values:
            sentinel_id = sentinel_scenario_id(source_id, condition)
            scenario_out_dir = batch_dir / "scenarios" / sentinel_id
            if scenario_out_dir.exists() and rerun_existing:
                shutil.rmtree(scenario_out_dir)
            if not scenario_out_dir.exists():
                shutil.copytree(source_scenario_dir, scenario_out_dir)
                _remove_previous_run_artifacts(scenario_out_dir)
            payload = _sentinel_skeleton_payload(
                source_scenario_dir=source_scenario_dir,
                source_id=source_id,
                sentinel_id=sentinel_id,
                condition=condition,
            )
            _write_json(scenario_out_dir / "skeleton_payload.json", payload)
            sentinel_inputs.append(
                BatchScenarioInput(
                    scenario_id=sentinel_id,
                    bundle_dir=scenario_out_dir / "bundle",
                    skeleton_payload=payload,
                )
            )
            scenario_pairs.append(
                {
                    "scenario_id": sentinel_id,
                    "source_scenario_id": source_id,
                    "condition": condition,
                }
            )

    task_distribution = build_task_distribution(
        sentinel_inputs,
        selection_strategy="condition-sentinel",
    )
    _write_batch_selection(
        batch_dir=batch_dir,
        batch_id=batch_id,
        source_batch_dir=source_batch_dir,
        source_report=source_report,
        scenario_pairs=scenario_pairs,
        task_distribution=task_distribution,
    )

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
    simulation_usage = TokenUsage(model=agent_model)

    for batch_input, pair in zip(sentinel_inputs, scenario_pairs):
        scenario_out_dir = batch_dir / "scenarios" / batch_input.scenario_id
        simulation = _load_existing_simulation_result(scenario_out_dir)
        if simulation is None or rerun_existing:
            simulation = run_simulation_for_bundle(
                scenario_id=batch_input.scenario_id,
                bundle_dir=batch_input.bundle_dir,
                agent_model=agent_model,
                runner=simulation_runner,
                condition=pair["condition"],
            )
            _write_json(
                scenario_out_dir / "simulation_result.json",
                simulation.model_dump(mode="json"),
            )
        simulation_usage = simulation_usage.add(simulation.usage)
        acceptance_error = _simulation_acceptance_error(
            simulation,
            batch_input.scenario_id,
            scenario_out_dir,
        )
        if not acceptance_error and _is_accepted_simulation(
            simulation,
            batch_input.scenario_id,
            scenario_out_dir,
        ):
            accepted_scenario_ids.append(batch_input.scenario_id)
            _record_accepted_task_outcome(
                scenario_id=batch_input.scenario_id,
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
                "scenario_id": batch_input.scenario_id,
                "source_scenario_id": pair["source_scenario_id"],
                "condition": pair["condition"],
                "status": simulation.status if simulation is not None else "missing",
                "error": acceptance_error or (simulation.error if simulation else ""),
            }
        )
        scorecard = _read_optional_json(
            scenario_out_dir / "bundle" / "run" / "run_scorecard.json"
        )
        if isinstance(scorecard, dict):
            _append_scorecard_digest(
                scenario_scorecard_digests,
                _scenario_scorecard_digest(
                    scenario_id=batch_input.scenario_id,
                    scenario_out_dir=scenario_out_dir,
                    scorecard=scorecard,
                ),
            )

    _normalize_collaboration_attribution_against_baseline(
        accepted_task_failure_ids=accepted_task_failure_ids,
        attack_success_ids=attack_success_ids,
        attack_resisted_ids=attack_resisted_ids,
        attack_unresolved_ids=attack_unresolved_ids,
        collaboration_attack_success_ids=collaboration_attack_success_ids,
        attack_classification_details=attack_classification_details,
    )
    _normalize_attack_attempt_denominators(
        attack_attempt_ids=attack_attempt_ids,
        attack_classification_details=attack_classification_details,
    )
    return build_batch_report(
        batch_id=batch_id,
        scenario_ids=[item.scenario_id for item in sentinel_inputs],
        accepted_scenario_ids=accepted_scenario_ids,
        failed_scenarios=failed_scenarios,
        usage=BatchUsage(
            construction=TokenUsage(model=construction_model),
            simulation=simulation_usage,
        ),
        stop_for_review=True,
        condition="mixed" if len(condition_values) > 1 else condition_values[0],
        base_task_ids=list(dict.fromkeys(_base_task_id(item) for item in sentinel_inputs)),
        construction_unit="condition_sentinel_run",
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
        task_distribution=task_distribution,
    )


def sentinel_scenario_id(source_scenario_id: str, condition: str) -> str:
    return f"{source_scenario_id}--{condition}"


def write_condition_sentinel_report(report: BatchReport, batch_dir: Path) -> Path:
    path = Path(batch_dir) / "batch_report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, report.model_dump(mode="json"))
    return path


def _source_batch_report(source_batch_dir: Path) -> dict[str, Any]:
    report_path = source_batch_dir / "batch_report.json"
    if not report_path.exists():
        raise FileNotFoundError(f"missing source batch report: {report_path}")
    return _read_json(report_path)


def _selected_source_scenario_ids(
    *,
    source_report: dict[str, Any],
    explicit_ids: list[str] | None,
    limit: int,
) -> list[str]:
    if explicit_ids:
        return list(dict.fromkeys(explicit_ids))
    accepted_ids = source_report.get("accepted_scenario_ids")
    if not isinstance(accepted_ids, list):
        raise ValueError("source batch report missing accepted_scenario_ids")
    selected = [item for item in accepted_ids if isinstance(item, str) and item]
    if limit <= 0:
        raise ValueError("limit must be positive")
    return selected[:limit]


def _condition_values(
    conditions: list[str | AuditCondition] | None,
) -> list[str]:
    raw_values = conditions or [
        AuditCondition.BASELINE,
        AuditCondition.PASSIVE,
        AuditCondition.ENFORCE,
    ]
    values = [
        value.value if isinstance(value, AuditCondition) else str(value)
        for value in raw_values
    ]
    deduped = list(dict.fromkeys(values))
    for value in deduped:
        AuditCondition(value)
    return deduped


def _source_model(source_report: dict[str, Any], *, usage_key: str) -> str:
    usage = source_report.get("usage")
    if isinstance(usage, dict):
        usage_section = usage.get(usage_key)
        if isinstance(usage_section, dict):
            model = usage_section.get("model")
            if isinstance(model, str) and model:
                return model
    return "gpt-5.2" if usage_key == "construction" else "gpt-4.1-mini"


def _sentinel_skeleton_payload(
    *,
    source_scenario_dir: Path,
    source_id: str,
    sentinel_id: str,
    condition: str,
) -> dict[str, Any]:
    payload = _read_optional_json(source_scenario_dir / "skeleton_payload.json")
    payload = dict(payload) if isinstance(payload, dict) else {}
    payload["scenario_id"] = sentinel_id
    payload["source_scenario_id"] = source_id
    payload["condition"] = condition
    row = payload.get("index_row")
    if isinstance(row, dict):
        row = dict(row)
        row["scenario_id"] = sentinel_id
        row["source_scenario_id"] = source_id
        row["condition"] = condition
        payload["index_row"] = row
    return payload


def _write_batch_selection(
    *,
    batch_dir: Path,
    batch_id: str,
    source_batch_dir: Path,
    source_report: dict[str, Any],
    scenario_pairs: list[dict[str, str]],
    task_distribution: BatchTaskDistribution,
) -> None:
    _write_json(
        batch_dir / "batch_selection.json",
        {
            "batch_id": batch_id,
            "selection_strategy": "condition-sentinel",
            "source_batch_dir": str(source_batch_dir),
            "source_batch_id": source_report.get("batch_id") or source_batch_dir.name,
            "conditions": list(dict.fromkeys(pair["condition"] for pair in scenario_pairs)),
            "scenario_ids": [pair["scenario_id"] for pair in scenario_pairs],
            "source_scenario_ids": list(
                dict.fromkeys(pair["source_scenario_id"] for pair in scenario_pairs)
            ),
            "scenario_condition_pairs": scenario_pairs,
            "base_task_ids": list(
                dict.fromkeys(
                    _base_task_id_from_pair(batch_dir, pair)
                    for pair in scenario_pairs
                )
            ),
            "task_distribution": task_distribution.model_dump(mode="json"),
        },
    )


def _base_task_id_from_pair(batch_dir: Path, pair: dict[str, str]) -> str:
    payload = _read_optional_json(
        batch_dir / "scenarios" / pair["scenario_id"] / "skeleton_payload.json"
    )
    if isinstance(payload, dict):
        row = payload.get("index_row")
        if isinstance(row, dict):
            base_task_id = row.get("base_task_id")
            if isinstance(base_task_id, str) and base_task_id:
                return base_task_id
    return pair["source_scenario_id"]


def _base_task_id(batch_input: BatchScenarioInput) -> str:
    row = batch_input.skeleton_payload.get("index_row")
    if isinstance(row, dict):
        base_task_id = row.get("base_task_id")
        if isinstance(base_task_id, str) and base_task_id:
            return base_task_id
    source_id = batch_input.skeleton_payload.get("source_scenario_id")
    return source_id if isinstance(source_id, str) and source_id else batch_input.scenario_id


def _remove_previous_run_artifacts(scenario_out_dir: Path) -> None:
    for path in (
        scenario_out_dir / "simulation_result.json",
        scenario_out_dir / "bundle" / "run",
    ):
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
