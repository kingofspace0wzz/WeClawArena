"""Run the tau2_retail owned-ecosystem stress calibration slice through Docker.

Mirrors ``run_bargaining_stress_calibration.py`` but filters
``family_id == "tau2_retail"`` rows from the v2 store manifest. The
24 base scenarios (4 archetypes x 6 tasks) plus 5 attack modes give
120 rows. This runner does not apply the global Phase-5 batch-size
assertions.

Defaults:
- ``--store benchmark/scenarios/v2.0.0``
- ``--out-dir benchmark/phase5/pilot/tau2_retail_owned_ecosystem_no_attacker_<date>``
- ``--max-turns 36`` (matches bargaining cap; per-bundle max_turns from
  scenario.json overrides downstream as needed)
- ``--audit-condition passive``
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
DEFAULT_OUT_DIR = Path("benchmark/phase5/pilot/tau2_retail_owned_ecosystem_no_attacker_20260517")
DEFAULT_MAX_TURNS = 36
RESULTS_FILENAME = "TAU2_RETAIL_STRESS_RESULTS.jsonl"
SUMMARY_FILENAME = "TAU2_RETAIL_STRESS_REPORT.json"
AXES = ("collaboration", "security", "privacy", "governance")


def select_retail_rows(
    manifest: dict[str, Any],
    *,
    include_baseline: bool = True,
    modes: set[str] | None = None,
    base_ids: set[str] | None = None,
    archetypes: set[str] | None = None,
) -> list[dict[str, Any]]:
    rows = list(manifest.get("rows") or manifest.get("main") or [])
    selected: list[dict[str, Any]] = []
    for row in rows:
        if row.get("family_id") != "tau2_retail":
            continue
        if not include_baseline and row.get("attack_mode") == "no_attacker":
            continue
        if modes is not None and row.get("attack_mode") not in modes:
            continue
        if base_ids is not None and row.get("base_id") not in base_ids:
            continue
        if archetypes is not None:
            base = str(row.get("base_id") or "")
            if not any(base.startswith(a + "__") for a in archetypes):
                continue
        selected.append(dict(row))
    return selected


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

    archetype_rates: dict[str, float | None] = {}
    for archetype in ("shared_account", "cross_account", "store_rep_dyad", "hub_aggregator"):
        archetype_results = [
            r for r in results
            if str(getattr(r, "base_id", "") or "").startswith(archetype + "__")
        ]
        archetype_rates[archetype] = _raw_bool_rate(
            [r.task_success for r in archetype_results]
        )

    return {
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
        "task_success_rate_by_archetype": archetype_rates,
        "attack_success_rate": _bool_rate(
            [r.attack_success for r in attacked if r.attack_success is not None]
        ),
        "attack_success_rate_by_axis": axis_rates,
        "axis_counts": axis_counts,
        "simulation_total_tokens": _simulation_total_tokens(results),
        "elapsed_seconds": round(elapsed_seconds, 3),
    }


def _raw_bool_rate(values: list) -> float | None:
    bools = [v for v in values if v is True or v is False]
    if not bools:
        return None
    return sum(1 for v in bools if v is True) / len(bools)


def _bool_rate(values: list) -> float | None:
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
        help="Drop no_attacker tau2_retail rows from the calibration slice.",
    )
    parser.add_argument(
        "--baseline-only",
        action="store_true",
        help=(
            "Keep only no_attacker rows (24-row no-attacker baseline). "
            "Convenience for the Task 30/31 smoke + gate batches."
        ),
    )
    parser.add_argument(
        "--modes",
        default="",
        help=(
            "Comma-separated attack modes to run, e.g. security,governance. "
            "Empty means all retail modes."
        ),
    )
    parser.add_argument(
        "--archetype",
        action="append",
        default=[],
        help=(
            "Restrict to one or more archetypes. "
            "Choices: shared_account, cross_account, store_rep_dyad, hub_aggregator. "
            "Can be supplied multiple times."
        ),
    )
    parser.add_argument(
        "--base-id",
        action="append",
        default=[],
        help=(
            "Base id to run, e.g. shared_account__t0. "
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
    if args.baseline_only and args.attack_only:
        parser.error("--baseline-only and --attack-only are mutually exclusive")
    modes_arg: set[str] | None
    if args.baseline_only:
        modes_arg = {"no_attacker"}
    else:
        modes_arg = {
            item.strip()
            for item in str(args.modes or "").split(",")
            if item.strip()
        } or None
    base_ids = {item.strip() for item in args.base_id if item.strip()} or None
    archetypes = {item.strip() for item in args.archetype if item.strip()} or None
    rows = select_retail_rows(
        manifest,
        include_baseline=not args.attack_only,
        modes=modes_arg,
        base_ids=base_ids,
        archetypes=archetypes,
    )
    if args.limit is not None:
        rows = rows[: args.limit]
    if not rows:
        print("No tau2_retail rows matched the filters.", file=sys.stderr)
        return 1
    if not args.quiet:
        print(f"Selected {len(rows)} tau2_retail row(s) for execution.")
        modes_seen = sorted({r["attack_mode"] for r in rows})
        archetypes_seen = sorted({r["base_id"].split("__")[0] for r in rows})
        print(f"  attack modes: {modes_seen}")
        print(f"  archetypes: {archetypes_seen}")
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
