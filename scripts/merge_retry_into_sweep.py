"""Merge retry RESULTS.jsonl back into the original sweep RESULTS.jsonl.

For each scenario directory under a sweep root, look for a sibling
``<scenario>_retry/`` directory and, when present, replace any row in
the original results whose ``variant_id`` is also present in the
retry results. Writes:

- ``<original>/BATCH_02_standard_RESULTS.merged.jsonl`` (or
  ``BARGAINING_STRESS_RESULTS.merged.jsonl`` for bargaining)
- ``<original>/BATCH_02_standard_REPORT.merged.json`` (or
  ``BARGAINING_STRESS_REPORT.merged.json``) — a small summary block
  containing only the headline numbers.

The original files are left untouched.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clawsocialarena.orchestrator.phase5_executor import ScenarioResult  # noqa: E402
from clawsocialarena.orchestrator.phase5_orchestrator import (  # noqa: E402
    _summarize_results,
)
from clawsocialarena.orchestrator.phase5_run_batches import run_batch_for  # noqa: E402

from scripts.run_bargaining_stress_calibration import (  # noqa: E402
    summarize_results as summarize_bargaining,
)


PHASE5_FAMILIES = {"marble_bidding", "swebench_workspace", "travel"}
BARGAINING_FAMILY = "marble_bargaining"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _merge_by_variant_id(
    original: list[dict[str, Any]], retry: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    retry_by_id = {str(r.get("variant_id")): r for r in retry}
    merged: list[dict[str, Any]] = []
    replaced = 0
    for row in original:
        vid = str(row.get("variant_id"))
        if vid in retry_by_id:
            merged.append(retry_by_id[vid])
            replaced += 1
        else:
            merged.append(row)
    return merged, replaced


def _dict_to_scenario_result(row: dict[str, Any]) -> ScenarioResult:
    known = {
        "variant_id","base_scenario_id","cell_id","family_id","task_index",
        "tier_index","attack_mode","attack_recipe","naturalization_success",
        "task_success","attack_success_collaboration","attack_success_security",
        "attack_success_privacy","attack_success_governance","attack_success",
        "governance_violation","privacy_violation","compliance_ok",
        "saf_recoverability","saf_policy_checkability","saf_attribution",
        "saf_evidence_integrity","saf_phase_scoped_policy","saf_identity_governance",
        "saf_overall","turn_count","hit_turn_cap","tool_call_count",
        "elapsed_seconds","naturalization_usage","simulation_usage","error",
        "transcript_path","extra",
    }
    kwargs = {k: row.get(k) for k in known if k in row}
    kwargs.setdefault("naturalization_usage", row.get("naturalization_usage") or {})
    kwargs.setdefault("simulation_usage", row.get("simulation_usage") or {})
    kwargs.setdefault("extra", row.get("extra") or {})
    return ScenarioResult(**kwargs)


def _summarize_phase5(merged: list[dict[str, Any]]) -> dict[str, Any]:
    spec = run_batch_for(2)
    object.__setattr__(spec, "expected_rows", len(merged))
    object.__setattr__(spec, "expected_rows_alternatives", ())
    results = [_dict_to_scenario_result(r) for r in merged]
    summary = _summarize_results(spec=spec, results=results, elapsed_seconds=0.0)
    return asdict(summary)


def _summarize_bargaining(
    merged: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = list(merged)  # the bargaining summarizer reads dicts via attribute access; build SRs
    sr_results = [_dict_to_scenario_result(r) for r in merged]
    return summarize_bargaining(rows=rows, results=sr_results, elapsed_seconds=0.0)


def _merge_one(scenario_dir: Path, retry_dir: Path, family: str) -> None:
    is_bargaining = family == BARGAINING_FAMILY
    if is_bargaining:
        results_name = "BARGAINING_STRESS_RESULTS.jsonl"
        report_name = "BARGAINING_STRESS_REPORT.json"
    else:
        results_name = "BATCH_02_standard_RESULTS.jsonl"
        report_name = "BATCH_02_standard_REPORT.json"

    original_path = scenario_dir / results_name
    retry_path = retry_dir / results_name
    if not original_path.exists():
        print(f"  [{scenario_dir.name}] no original results at {original_path}")
        return
    if not retry_path.exists():
        print(f"  [{scenario_dir.name}] no retry results at {retry_path}; skipping")
        return

    original = _load_jsonl(original_path)
    retry = _load_jsonl(retry_path)
    merged, replaced = _merge_by_variant_id(original, retry)
    print(
        f"  [{scenario_dir.name}] original={len(original)} retry={len(retry)} "
        f"replaced={replaced}"
    )

    merged_jsonl = scenario_dir / results_name.replace(".jsonl", ".merged.jsonl")
    with merged_jsonl.open("w") as f:
        for row in merged:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")

    if is_bargaining:
        summary = _summarize_bargaining(merged)
        headline = {
            "rows_total": summary["rows_total"],
            "rows_errored": summary["rows_errored"],
            "rows_hit_turn_cap": summary["rows_hit_turn_cap"],
            "task_success_rate_baseline": summary["task_success_rate_baseline"],
            "task_success_rate_attacker": summary["task_success_rate_attacker"],
            "attack_success_rate": summary["attack_success_rate"],
            "turn_cap_rate": summary["turn_cap_rate"],
            "mean_turn_count": summary["mean_turn_count"],
        }
    else:
        summary = _summarize_phase5(merged)
        headline = {
            "n_run": summary["n_run"],
            "n_errors": summary["n_errors"],
            "n_baseline": summary.get("n_baseline"),
            "n_attacker": summary.get("n_attacker"),
            "task_success_rate_baseline": summary.get("task_success_rate_baseline"),
            "task_success_rate_attacker": summary.get("task_success_rate_attacker"),
            "attack_success_rate": summary.get("attack_success_rate"),
        }

    merged_report = scenario_dir / report_name.replace(".json", ".merged.json")
    merged_report.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(f"  [{scenario_dir.name}] headline: {json.dumps(headline, sort_keys=True)}")
    print(f"  [{scenario_dir.name}] -> {merged_jsonl.name}, {merged_report.name}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge retry RESULTS.jsonl back into original sweep dirs.",
    )
    parser.add_argument(
        "--run-dir", required=True, type=Path,
        help="Sweep root containing <scenario>/ and <scenario>_retry/ pairs.",
    )
    parser.add_argument(
        "--scenarios", nargs="+",
        default=[
            "bargaining_opus47",
            "bidding_opus47",
            "swebench_workspace_opus47",
            "travel_opus47",
        ],
        help="Original scenario directory names. A sibling <name>_retry/ "
             "is expected next to each one.",
    )
    args = parser.parse_args()

    families = {
        "bargaining_opus47": BARGAINING_FAMILY,
        "bidding_opus47": "marble_bidding",
        "swebench_workspace_opus47": "swebench_workspace",
        "travel_opus47": "travel",
    }
    for scen in args.scenarios:
        family = families.get(scen)
        if family is None:
            print(f"  [{scen}] unknown scenario; skipping")
            continue
        _merge_one(
            scenario_dir=args.run_dir / scen,
            retry_dir=args.run_dir / f"{scen}_retry",
            family=family,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
