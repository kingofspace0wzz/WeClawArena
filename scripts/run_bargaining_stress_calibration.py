"""Run the MARBLE bargaining stress-calibration slice through Docker.

This runner is intentionally separate from ``run_phase5_pilot.py``. It
selects only ``family_id == "marble_bargaining"`` rows from a v2 store
manifest and does not apply the global Phase-5 batch-size assertions.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from clawsocialarena.generator.phase5_manifest import load_manifest  # noqa: E402
from clawsocialarena.orchestrator.phase5_docker_executor import (  # noqa: E402
    DriverOrchestratedDockerExecutor,
    PHASE5_DEFAULT_AGENT_MODEL,
)
from clawsocialarena.orchestrator.phase5_executor import (  # noqa: E402
    ScenarioExecutor,
    ScenarioResult,
)
from clawsocialarena.types import AuditCondition  # noqa: E402


DEFAULT_STORE_DIR = Path("benchmark/scenarios/v2.0.0")
DEFAULT_OUT_DIR = Path("benchmark/phase5/pilot/bargaining_owned_ecosystem_5_modes_cap36_20260516")
DEFAULT_MAX_TURNS = 36
RESULTS_FILENAME = "BARGAINING_STRESS_RESULTS.jsonl"
SUMMARY_FILENAME = "BARGAINING_STRESS_REPORT.json"
AXES = ("collaboration", "security", "privacy", "governance")


def select_bargaining_rows(
    manifest: dict[str, Any],
    *,
    include_baseline: bool = True,
    modes: set[str] | None = None,
    base_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    rows = list(manifest.get("rows") or manifest.get("main") or [])
    selected: list[dict[str, Any]] = []
    for row in rows:
        if row.get("family_id") != "marble_bargaining":
            continue
        if not include_baseline and row.get("attack_mode") == "no_attacker":
            continue
        if modes is not None and row.get("attack_mode") not in modes:
            continue
        if base_ids is not None and row.get("base_id") not in base_ids:
            continue
        selected.append(dict(row))
    return selected


def bargaining_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return select_bargaining_rows(manifest)


def run_calibration_rows(
    *,
    rows: list[dict[str, Any]],
    executor: ScenarioExecutor,
    store_dir: Path,
    out_dir: Path,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / RESULTS_FILENAME
    summary_path = out_dir / SUMMARY_FILENAME
    started = time.monotonic()

    results: list[ScenarioResult] = []
    with results_path.open("w", encoding="utf-8") as f:
        for row in rows:
            result = executor.execute(row=row, base_dir=store_dir)
            results.append(result)
            f.write(json.dumps(asdict(result), sort_keys=True) + "\n")
            f.flush()

    summary = summarize_results(
        rows=rows,
        results=results,
        elapsed_seconds=time.monotonic() - started,
    )
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def summarize_results(
    *,
    rows: list[dict[str, Any]],
    results: list[ScenarioResult],
    elapsed_seconds: float,
) -> dict[str, Any]:
    baseline = [r for r in results if r.attack_mode == "no_attacker"]
    attacked = [r for r in results if r.attack_mode != "no_attacker"]
    errored = [r for r in results if r.error]
    axis_rates: dict[str, float | None] = {}
    axis_counts: dict[str, dict[str, int]] = {}
    for axis in AXES:
        values = [
            getattr(r, f"attack_success_{axis}")
            for r in results
            if getattr(r, f"attack_success_{axis}") is not None
        ]
        axis_counts[axis] = {
            "n": len(values),
            "success": sum(1 for value in values if value is True),
        }
        axis_rates[axis] = _bool_rate(values)

    summary = {
        "rows_total": len(results),
        "manifest_rows_selected": len(rows),
        "rows_errored": len(errored),
        "rows_failed_before_scorecard": sum(
            1 for r in results if r.task_success is None
        ),
        "rows_hit_turn_cap": sum(1 for r in results if r.hit_turn_cap is True),
        "task_success_rate_baseline": _raw_bool_rate(
            [r.task_success for r in baseline]
        ),
        "task_success_rate_attacker": _raw_bool_rate(
            [r.task_success for r in attacked]
        ),
        "attack_success_rate": _bool_rate(
            [r.attack_success for r in attacked if r.attack_success is not None]
        ),
        "attack_success_rate_by_axis": axis_rates,
        "attack_success_counts_by_axis": axis_counts,
        "turn_cap_rate": _bool_rate([r.hit_turn_cap for r in results]),
        "mean_turn_count": _mean([r.turn_count for r in results]),
        "simulation_total_tokens": _simulation_total_tokens(results),
        "elapsed_seconds": elapsed_seconds,
        "deterministic_asr_deprecated": True,
        "asr_reporting_policy": (
            "For MARBLE bargaining, deterministic attack-success fields are "
            "diagnostics only. Report LLM-ASR as the bargaining ASR metric."
        ),
    }
    summary["by_mode"] = summarize_bargaining_stress_results(
        [asdict(result) for result in results]
    )["by_mode"]
    return summary


def summarize_bargaining_stress_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_mode: dict[str, dict[str, Any]] = {}
    for row in rows:
        mode = str(row.get("attack_mode") or "no_attacker")
        bucket = by_mode.setdefault(
            mode,
            {
                "n": 0,
                "attack_success": 0,
                "attack_denominator": 0,
                "substrate_blocked": 0,
            },
        )
        bucket["n"] += 1
        if row.get("attack_success") is not None:
            bucket["attack_denominator"] += 1
            if row.get("attack_success") is True:
                bucket["attack_success"] += 1
        extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
        if extra.get("bargaining_stress_substrate_blocked") is True:
            bucket["substrate_blocked"] += 1
    for bucket in by_mode.values():
        denom = bucket["attack_denominator"]
        bucket["asr"] = round(bucket["attack_success"] / denom, 4) if denom else None
    return {"n_rows": len(rows), "by_mode": by_mode}


def _bool_rate(values: list[bool | None]) -> float | None:
    defined = [value for value in values if value is not None]
    if not defined:
        return None
    return sum(1 for value in defined if value is True) / len(defined)


def _raw_bool_rate(values: list[bool | None]) -> float | None:
    if not values:
        return None
    return sum(1 for value in values if value is True) / len(values)


def _mean(values: list[int | float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _simulation_total_tokens(results: list[ScenarioResult]) -> int:
    total = 0
    for result in results:
        usage = result.simulation_usage or {}
        if "total_tokens" in usage:
            total += int(usage.get("total_tokens") or 0)
        else:
            total += int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
            total += int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    return total


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--agent-model", default=PHASE5_DEFAULT_AGENT_MODEL)
    parser.add_argument("--max-turns", "--turn-cap", type=int, default=DEFAULT_MAX_TURNS)
    parser.add_argument(
        "--simulation-attempts",
        type=int,
        default=1,
        help="Attempts per row passed to the Docker simulation runner.",
    )
    parser.add_argument(
        "--audit-condition",
        choices=[value.value for value in AuditCondition],
        default=AuditCondition.PASSIVE.value,
    )
    parser.add_argument(
        "--attack-only",
        action="store_true",
        help="Drop no_attacker bargaining rows from the calibration slice.",
    )
    parser.add_argument(
        "--modes",
        default="",
        help=(
            "Comma-separated attack modes to run, e.g. security,governance. "
            "Empty means all bargaining modes."
        ),
    )
    parser.add_argument(
        "--base-id",
        action="append",
        default=[],
        help=(
            "Base id to run, e.g. CU-A-marble_bargaining__t1. "
            "Can be supplied multiple times."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N selected rows.",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    manifest = load_manifest(args.store / "manifest.json")
    modes = {
        item.strip()
        for item in str(args.modes or "").split(",")
        if item.strip()
    } or None
    base_ids = {item.strip() for item in args.base_id if item.strip()} or None
    rows = select_bargaining_rows(
        manifest,
        include_baseline=not args.attack_only,
        modes=modes,
        base_ids=base_ids,
    )
    if args.limit is not None:
        rows = rows[: args.limit]
    executor = DriverOrchestratedDockerExecutor(
        store_dir=args.store,
        run_dir=args.out_dir,
        agent_model=args.agent_model,
        audit_condition=AuditCondition(args.audit_condition),
        simulation_attempts=args.simulation_attempts,
        max_turns_override=args.max_turns,
    )
    summary = run_calibration_rows(
        rows=rows,
        executor=executor,
        store_dir=args.store,
        out_dir=args.out_dir,
    )
    if not args.quiet:
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
