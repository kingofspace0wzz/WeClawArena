from __future__ import annotations

import argparse
import copy
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from clawsocialarena.generator.naturalization import (
    NaturalizationValidationError,
    NaturalizationPatch,
    sanitize_naturalization_patch_against_skeleton,
    sanitize_relative_date_phrases_in_value,
    run_naturalization,
    valid_window_start_date,
)
from clawsocialarena.gateway.compose_runner import docker_available
from clawsocialarena.llm.costing import TokenUsage
from clawsocialarena.llm.openai_client import (
    OpenAIConfig,
    OpenAIResponsesJsonClient,
    require_openai_key,
)
from clawsocialarena.llm.retry import is_transient_llm_error
from clawsocialarena.simulation.batch_runner import (
    BatchScenarioInput,
    BatchUsage,
    _load_existing_naturalization_patch,
    _naturalization_resource_coverage_errors,
    build_task_distribution,
    build_batch_report,
    run_naturalization_simulation_batch,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Naturalize and simulate one benchmark batch."
    )
    defaults = OpenAIConfig()
    parser.add_argument("--batch-id", default="batch-0001")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument(
        "--batch-strategy",
        choices=("contiguous", "category-sweep"),
        default="contiguous",
    )
    parser.add_argument("--sweep-index", type=int, default=0)
    parser.add_argument("--out", type=Path, default=Path("benchmark/batches"))
    parser.add_argument(
        "--scenario-root",
        type=Path,
        default=Path("benchmark/scenarios/v1.0.0"),
    )
    parser.add_argument("--max-cost-usd", type=float, default=25.0)
    parser.add_argument("--construction-model", default=defaults.construction_model)
    parser.add_argument("--agent-model", default=defaults.agent_model)
    parser.add_argument("--naturalization-attempts", type=int, default=3)
    parser.add_argument("--simulation-attempts", type=int, default=2)
    parser.add_argument("--resume-existing", action="store_true")
    parser.add_argument("--rerun-simulations", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.start_index < 0:
        print("--start-index must be non-negative", file=sys.stderr)
        return 2
    if args.sweep_index < 0:
        print("--sweep-index must be non-negative", file=sys.stderr)
        return 2
    if args.max_cost_usd <= 0:
        print("--max-cost-usd must be positive", file=sys.stderr)
        return 2
    if args.naturalization_attempts <= 0:
        print("--naturalization-attempts must be positive", file=sys.stderr)
        return 2
    if args.simulation_attempts <= 0:
        print("--simulation-attempts must be positive", file=sys.stderr)
        return 2
    if not args.dry_run:
        try:
            require_openai_key()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if not docker_available():
            print("docker is required for paid simulation batches", file=sys.stderr)
            return 2
        batch_dir = args.out / args.batch_id
        inputs = _load_inputs_for_args(args)
        task_distribution = build_task_distribution(
            inputs,
            selection_strategy=args.batch_strategy,
            sweep_index=args.sweep_index
            if args.batch_strategy == "category-sweep"
            else None,
        )
        _write_report(
            batch_dir / "batch_selection.json",
            {
                "batch_id": args.batch_id,
                "selection_strategy": args.batch_strategy,
                "start_index": args.start_index,
                "sweep_index": args.sweep_index
                if args.batch_strategy == "category-sweep"
                else None,
                "scenario_ids": [item.scenario_id for item in inputs],
                "base_task_ids": list(
                    dict.fromkeys(_base_task_id(item) for item in inputs)
                ),
                "task_distribution": task_distribution.model_dump(mode="json"),
            },
        )
        client = OpenAIResponsesJsonClient()
        base_task_groups = _base_task_input_groups(inputs)
        base_task_payloads = _base_task_payloads(inputs)
        naturalization_cache: dict[str, NaturalizationPatch] = (
            _load_resume_base_naturalization_cache(
                batch_dir=batch_dir,
                inputs=inputs,
            )
            if args.resume_existing and _has_matched_base_tasks(inputs)
            else {}
        )

        def naturalizer(batch_input: BatchScenarioInput):
            base_task_id = _base_task_id(batch_input)
            if base_task_id in naturalization_cache:
                return _variant_patch_from_base(
                    naturalization_cache[base_task_id],
                    scenario_id=batch_input.scenario_id,
                    construction_model=args.construction_model,
                    charge_usage=False,
                    skeleton_payload=batch_input.skeleton_payload,
                )
            base_patch = _run_naturalization_with_resource_coverage_retry(
                client=client,
                scenario_id=base_task_id,
                skeleton_payload=base_task_payloads[base_task_id],
                model=args.construction_model,
                coverage_payloads=[
                    item.skeleton_payload for item in base_task_groups[base_task_id]
                ],
                max_attempts=args.naturalization_attempts,
            )
            naturalization_cache[base_task_id] = base_patch
            return _variant_patch_from_base(
                base_patch,
                scenario_id=batch_input.scenario_id,
                construction_model=args.construction_model,
                charge_usage=True,
                skeleton_payload=batch_input.skeleton_payload,
            )

        def variant_naturalizer(batch_input: BatchScenarioInput):
            return _run_naturalization_with_resource_coverage_retry(
                client=client,
                scenario_id=batch_input.scenario_id,
                skeleton_payload=batch_input.skeleton_payload,
                model=args.construction_model,
                coverage_payloads=[batch_input.skeleton_payload],
                max_attempts=args.naturalization_attempts,
            )

        report = run_naturalization_simulation_batch(
            batch_id=args.batch_id,
            inputs=inputs,
            construction_model=args.construction_model,
            agent_model=args.agent_model,
            out_dir=batch_dir,
            naturalizer=naturalizer if _has_matched_base_tasks(inputs) else variant_naturalizer,
            max_cost_usd=args.max_cost_usd,
            resume_existing=args.resume_existing,
            reuse_passed_simulations=not args.rerun_simulations,
            simulation_attempts=args.simulation_attempts,
            task_distribution=task_distribution,
        )
        _write_report(batch_dir / "batch_report.json", report.model_dump(mode="json"))
        print(report.decision)
        return 0

    scenario_ids = [f"pilot-placeholder-{idx:02d}" for idx in range(args.batch_size)]
    report = build_batch_report(
        batch_id=args.batch_id,
        scenario_ids=scenario_ids,
        accepted_scenario_ids=[],
        failed_scenarios=[],
        usage=BatchUsage(
            construction=TokenUsage(model=args.construction_model),
            simulation=TokenUsage(model=args.agent_model),
        ),
        stop_for_review=True,
    )
    report_path = args.out / args.batch_id / "batch_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    print(report.decision)
    return 0


def load_batch_inputs(
    *,
    scenario_root: Path,
    batch_size: int,
    start_index: int = 0,
    batch_strategy: str = "contiguous",
    sweep_index: int = 0,
) -> list[BatchScenarioInput]:
    return _load_batch_inputs(
        scenario_root=scenario_root,
        batch_size=batch_size,
        start_index=start_index,
        batch_strategy=batch_strategy,
        sweep_index=sweep_index,
    )


def _load_inputs_for_args(args: argparse.Namespace) -> list[BatchScenarioInput]:
    if args.batch_strategy == "category-sweep":
        return load_batch_inputs(
            scenario_root=args.scenario_root,
            batch_size=args.batch_size,
            start_index=args.start_index,
            batch_strategy=args.batch_strategy,
            sweep_index=args.sweep_index,
        )
    return load_batch_inputs(
        scenario_root=args.scenario_root,
        batch_size=args.batch_size,
        start_index=args.start_index,
    )


def _load_batch_inputs(
    *,
    scenario_root: Path,
    batch_size: int,
    start_index: int,
    batch_strategy: str,
    sweep_index: int,
) -> list[BatchScenarioInput]:
    index_path = scenario_root / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"missing scenario index: {index_path}")
    index = _read_json(index_path)
    rows = list(index.get("rows", []))
    if batch_strategy == "contiguous":
        selected = rows[start_index : start_index + batch_size]
    elif batch_strategy == "category-sweep":
        selected = _select_category_sweep_rows(
            rows=rows,
            batch_size=batch_size,
            sweep_index=sweep_index,
        )
    else:
        raise ValueError(f"unsupported batch strategy: {batch_strategy}")
    if len(selected) < batch_size:
        raise ValueError(
            f"requested {batch_size} scenarios from start_index {start_index} "
            f"but only {len(selected)} are available"
        )
    return [
        BatchScenarioInput(
            scenario_id=str(row["scenario_id"]),
            bundle_dir=scenario_root / str(row["bundle_path"]),
            skeleton_payload=build_skeleton_payload(
                scenario_root=scenario_root,
                row=row,
            ),
        )
        for row in selected
    ]


def _select_category_sweep_rows(
    *,
    rows: list[dict[str, Any]],
    batch_size: int,
    sweep_index: int,
) -> list[dict[str, Any]]:
    cell_order: list[tuple[str, str]] = []
    grouped: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        if row.get("stratum") != "main":
            continue
        category = str(row.get("category") or "")
        family = str(row.get("family") or "")
        base_task_id = str(row.get("base_task_id") or "")
        if not category or not family or not base_task_id:
            continue
        cell = (category, family)
        if cell not in grouped:
            grouped[cell] = {}
            cell_order.append(cell)
        grouped[cell].setdefault(base_task_id, []).append(row)
    selected: list[dict[str, Any]] = []
    for cell_index, cell in enumerate(cell_order):
        base_groups = list(grouped[cell].values())
        if not base_groups:
            continue
        selected.extend(base_groups[(sweep_index + cell_index) % len(base_groups)])
    if len(selected) != batch_size:
        raise ValueError(
            "category-sweep selected "
            f"{len(selected)} scenarios; pass --batch-size {len(selected)}"
        )
    return selected


def build_skeleton_payload(
    *,
    scenario_root: Path,
    row: dict[str, Any],
) -> dict[str, Any]:
    bundle_dir = scenario_root / str(row["bundle_path"])
    scenario = _read_json(bundle_dir / "scenario.json")
    gt = _read_json(bundle_dir / "scenario.gt.json")
    construction = gt.get("construction_manifest")
    scenario = _sanitize_scenario_for_naturalization(
        scenario=scenario,
        construction_manifest=construction,
    )
    payload = {
        "index_row": row,
        "scenario": scenario,
        "construction_manifest": construction,
        "terminal_predicate": gt.get("terminal_predicate"),
        "resource_manifest": gt.get("resource_manifest"),
        "resource_payloads": collect_resource_payloads(
            bundle_dir=bundle_dir,
            resource_manifest=gt.get("resource_manifest"),
        ),
        "governance_manifest": gt.get("governance_manifest"),
        "attack_plan": gt.get("attack_plan"),
        "invariants": gt.get("invariants"),
    }
    anchor = valid_window_start_date(payload)
    if anchor is not None:
        payload["resource_payloads"] = sanitize_relative_date_phrases_in_value(
            payload["resource_payloads"],
            anchor,
        )
    return payload


def _sanitize_scenario_for_naturalization(
    *,
    scenario: dict[str, Any],
    construction_manifest: Any,
) -> dict[str, Any]:
    if not isinstance(construction_manifest, dict):
        return scenario
    if construction_manifest.get("construction_mode") != "world_pack":
        return scenario
    sanitized = copy.deepcopy(scenario)
    agents = sanitized.get("agents")
    if not isinstance(agents, list):
        return sanitized
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        agent_id = agent.get("agent_id")
        prompt = agent.get("system_prompt_template")
        if not isinstance(agent_id, str) or not isinstance(prompt, str):
            continue
        agent["system_prompt_template"] = _sanitize_worldpack_prompt(
            agent_id=agent_id,
            prompt=prompt,
        )
    _rewrite_worldpack_opening_message_labels(sanitized)
    return sanitized


def _sanitize_worldpack_prompt(*, agent_id: str, prompt: str) -> str:
    agent_label = _agent_label_from_id(agent_id)
    stale_patterns = (
        f"You are {agent_label}'s personal agent",
        f"{agent_label} is available",
    )
    kept_lines = [
        line
        for line in prompt.splitlines()
        if not any(pattern in line for pattern in stale_patterns)
    ]
    return "\n".join(kept_lines).rstrip()


def _rewrite_worldpack_opening_message_labels(scenario: dict[str, Any]) -> None:
    display_names = _scenario_agent_display_names(scenario)
    if not display_names:
        return
    opening = scenario.get("opening_message")
    if isinstance(opening, dict):
        content = opening.get("content")
        if not isinstance(content, str):
            return
        normalized = _rewrite_legacy_agent_labels(content, display_names)
        if normalized != content:
            scenario["opening_message"] = {**opening, "content": normalized}
    elif isinstance(opening, str):
        normalized = _rewrite_legacy_agent_labels(opening, display_names)
        if normalized != opening:
            scenario["opening_message"] = normalized


def _scenario_agent_display_names(scenario: dict[str, Any]) -> dict[str, str]:
    agents = scenario.get("agents")
    if not isinstance(agents, list):
        return {}
    display_names: dict[str, str] = {}
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        agent_id = agent.get("agent_id")
        prompt = agent.get("system_prompt_template")
        if not isinstance(agent_id, str) or not isinstance(prompt, str):
            continue
        display_name = _display_name_from_worldpack_prompt(prompt)
        if display_name:
            display_names[agent_id] = display_name
    return display_names


def _rewrite_legacy_agent_labels(
    value: str,
    display_names: dict[str, str],
) -> str:
    normalized = value
    for agent_id, display_name in display_names.items():
        agent_label = _agent_label_from_id(agent_id)
        if not agent_label:
            continue
        normalized = re.sub(
            rf"\b{re.escape(agent_label)}\b",
            _display_first_name(display_name),
            normalized,
            flags=re.I,
        )
    return normalized


def _display_name_from_worldpack_prompt(prompt: str) -> str | None:
    match = re.search(
        r"\bacts?\s+for\s+([^(\n.]+?)(?:\s*\(|\.|\n|$)",
        prompt,
        flags=re.I,
    )
    if not match:
        return None
    display_name = " ".join(match.group(1).split())
    return display_name or None


def _display_first_name(display_name: str) -> str:
    return display_name.split()[0] if display_name.split() else display_name


def _agent_label_from_id(agent_id: str) -> str:
    return " ".join(
        part.capitalize() for part in re.split(r"[-_]+", agent_id) if part
    )


def collect_resource_payloads(
    *,
    bundle_dir: Path,
    resource_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(resource_manifest, dict):
        return {}
    resources = resource_manifest.get("resources")
    if not isinstance(resources, dict):
        return {}
    payloads: dict[str, Any] = {}
    resource_root = bundle_dir / "resources"
    for resource_id, entry in resources.items():
        if not isinstance(entry, dict):
            continue
        resource_path = entry.get("path")
        if not isinstance(resource_path, str) or not resource_path:
            continue
        materialized_path = _safe_resource_path(resource_root, resource_path)
        resource_type = entry.get("type")
        if resource_type == "file" and materialized_path.exists():
            payloads[str(resource_id)] = {
                "type": "file",
                "path": resource_path,
                "content": materialized_path.read_text(encoding="utf-8")[:20000],
            }
        elif resource_type == "sqlite_db" and materialized_path.exists():
            payloads[str(resource_id)] = {
                "type": "sqlite_db",
                "path": resource_path,
                "tables": _read_sqlite_tables(materialized_path),
            }
    return payloads


def _safe_resource_path(resource_root: Path, relative_path: str) -> Path:
    rel = Path(relative_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"resource path escapes resources/: {relative_path!r}")
    resolved = (resource_root / rel).resolve()
    if not resolved.is_relative_to(resource_root.resolve()):
        raise ValueError(f"resource path escapes resources/: {relative_path!r}")
    return resolved


def _read_sqlite_tables(path: Path) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {}
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        table_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
        for table_row in table_rows:
            table_name = str(table_row["name"])
            quoted = _quote_identifier(table_name)
            rows = conn.execute(f"SELECT * FROM {quoted} LIMIT 50").fetchall()
            tables[table_name] = [dict(row) for row in rows]
    return tables


def _quote_identifier(identifier: str) -> str:
    if not identifier.replace("_", "").isalnum() or not identifier:
        raise ValueError(f"invalid SQLite identifier: {identifier!r}")
    if identifier[0].isdigit():
        raise ValueError(f"invalid SQLite identifier: {identifier!r}")
    return '"' + identifier.replace('"', '""') + '"'


def _has_matched_base_tasks(inputs: list[BatchScenarioInput]) -> bool:
    return any(_base_task_id(item) != item.scenario_id for item in inputs)


def _run_naturalization_with_resource_coverage_retry(
    *,
    client: OpenAIResponsesJsonClient,
    scenario_id: str,
    skeleton_payload: dict[str, Any],
    model: str,
    coverage_payloads: list[dict[str, Any]],
    max_attempts: int,
) -> NaturalizationPatch:
    total_usage = TokenUsage(model=model)
    last_patch: NaturalizationPatch | None = None
    last_error: NaturalizationValidationError | None = None
    for attempt in range(max_attempts):
        try:
            patch = run_naturalization(
                client=client,
                scenario_id=scenario_id,
                skeleton_payload=skeleton_payload,
                model=model,
            )
        except NaturalizationValidationError as exc:
            total_usage = total_usage.add(exc.usage)
            last_error = exc
            continue
        except Exception as exc:
            if not is_transient_llm_error(exc):
                raise
            if attempt + 1 < max_attempts:
                continue
            raise NaturalizationValidationError(
                (
                    "transient naturalization error after "
                    f"{max_attempts} attempts: {exc}"
                ),
                usage=total_usage,
                raw_data={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "attempts": max_attempts,
                    "transient": True,
                },
            ) from exc
        total_usage = total_usage.add(patch.usage)
        patch = patch.model_copy(update={"usage": total_usage})
        last_patch = patch
        if not _naturalization_coverage_errors_for_payloads(
            coverage_payloads=coverage_payloads,
            patch=patch,
        ):
            return patch
    if last_patch is None:
        if last_error is not None:
            raise NaturalizationValidationError(
                str(last_error),
                usage=total_usage,
                raw_data=last_error.raw_data,
            ) from last_error
        raise RuntimeError("naturalization did not run")
    return last_patch


def _naturalization_coverage_errors_for_payloads(
    *,
    coverage_payloads: list[dict[str, Any]],
    patch: NaturalizationPatch,
) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for skeleton_payload in coverage_payloads:
        for error in _naturalization_resource_coverage_errors(
            skeleton_payload=skeleton_payload,
            patch=patch,
        ):
            if error not in seen:
                seen.add(error)
                errors.append(error)
    return errors


def _base_task_id(batch_input: BatchScenarioInput) -> str:
    index_row = batch_input.skeleton_payload.get("index_row")
    if isinstance(index_row, dict):
        base_task_id = index_row.get("base_task_id")
        if isinstance(base_task_id, str) and base_task_id:
            return base_task_id
    return batch_input.scenario_id


def _base_task_payloads(
    inputs: list[BatchScenarioInput],
) -> dict[str, dict[str, Any]]:
    grouped = _base_task_input_groups(inputs)
    return {
        base_task_id: _base_task_payload(base_task_id, items)
        for base_task_id, items in grouped.items()
    }


def _base_task_input_groups(
    inputs: list[BatchScenarioInput],
) -> dict[str, list[BatchScenarioInput]]:
    grouped: dict[str, list[BatchScenarioInput]] = {}
    for batch_input in inputs:
        grouped.setdefault(_base_task_id(batch_input), []).append(batch_input)
    return grouped


def _load_resume_base_naturalization_cache(
    *,
    batch_dir: Path,
    inputs: list[BatchScenarioInput],
) -> dict[str, NaturalizationPatch]:
    cache: dict[str, NaturalizationPatch] = {}
    for base_task_id, group in _base_task_input_groups(inputs).items():
        fallback_patch: NaturalizationPatch | None = None
        coverage_payloads = [item.skeleton_payload for item in group]
        for batch_input in group:
            patch = _load_existing_naturalization_patch(
                batch_dir / "scenarios" / batch_input.scenario_id,
                batch_input.skeleton_payload,
            )
            if patch is None:
                continue
            if _naturalization_coverage_errors_for_payloads(
                coverage_payloads=coverage_payloads,
                patch=patch,
            ):
                continue
            if patch.usage.input_tokens or patch.usage.output_tokens:
                cache[base_task_id] = patch
                break
            if fallback_patch is None:
                fallback_patch = patch
        else:
            if fallback_patch is not None:
                cache[base_task_id] = fallback_patch
    return cache


def _base_task_payload(
    base_task_id: str,
    inputs: list[BatchScenarioInput],
) -> dict[str, Any]:
    representative = _representative_base_input(inputs)
    representative_payload = dict(representative.skeleton_payload)
    payload = {
        "naturalization_scope": "base_task",
        "base_task_id": base_task_id,
        "representative_scenario_id": representative.scenario_id,
        "representative_skeleton": representative_payload,
        "matched_variants": [
            _variant_summary(batch_input) for batch_input in inputs
        ],
    }
    for key in ("resource_payloads", "resource_manifest"):
        value = representative_payload.get(key)
        if value:
            payload[key] = value
    return payload


def _representative_base_input(
    inputs: list[BatchScenarioInput],
) -> BatchScenarioInput:
    for batch_input in inputs:
        index_row = batch_input.skeleton_payload.get("index_row")
        if isinstance(index_row, dict) and index_row.get("attack_mode") == "no_attacker":
            return batch_input
    return inputs[0]


def _variant_summary(batch_input: BatchScenarioInput) -> dict[str, Any]:
    index_row = batch_input.skeleton_payload.get("index_row")
    if not isinstance(index_row, dict):
        return {"scenario_id": batch_input.scenario_id}
    return {
        "scenario_id": batch_input.scenario_id,
        "attack_mode": index_row.get("attack_mode"),
        "attack_axis": index_row.get("attack_axis"),
        "attack_type": index_row.get("attack_type"),
    }


def _variant_patch_from_base(
    base_patch: NaturalizationPatch,
    *,
    scenario_id: str,
    construction_model: str,
    charge_usage: bool,
    skeleton_payload: dict[str, Any],
) -> NaturalizationPatch:
    usage = (
        base_patch.usage
        if charge_usage
        else TokenUsage(model=construction_model)
    )
    data = base_patch.model_dump(mode="json")
    data.update(
        {
            "scenario_id": scenario_id,
            "usage": usage.model_dump(mode="json"),
        }
    )
    data = sanitize_naturalization_patch_against_skeleton(data, skeleton_payload)
    return NaturalizationPatch.model_validate(data)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
