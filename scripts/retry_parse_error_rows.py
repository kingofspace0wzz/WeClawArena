"""Re-run only the parse-error rows from a prior Bedrock sweep.

Reads ``<run_dir>/retry_index.json`` (one entry per scenario, listing
the parse-error variant_ids), filters the v2 store manifest down to
those rows, and invokes the same machinery the original sweep used:

- ``marble_bidding``, ``swebench_workspace``, ``travel`` go through
  ``run_run_batch`` with batch 2's standard selector, after relaxing
  the batch's ``expected_rows`` to the slim slice's count.
- ``marble_bargaining`` goes through ``run_calibration_rows`` with a
  hand-trimmed row list (the stress runner has no batch selector).

Output lands under ``<run_dir>/<scenario>_<model_tag>_retry/`` with
the same RESULTS / REPORT filenames as the original sweep so the
downstream merge step can fold them back in.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clawsocialarena.generator.phase5_manifest import load_manifest  # noqa: E402
from clawsocialarena.orchestrator.phase5_docker_executor import (  # noqa: E402
    DriverOrchestratedDockerExecutor,
)
from clawsocialarena.orchestrator.phase5_orchestrator import (  # noqa: E402
    run_run_batch,
)
from clawsocialarena.orchestrator.phase5_run_batches import (  # noqa: E402
    run_batch_for,
)

# Re-use the slim-store normalizer from the pilot runner.
from scripts.run_phase5_pilot import (  # noqa: E402
    normalize_store_manifest_for_batches,
)
from scripts.run_bargaining_stress_calibration import (  # noqa: E402
    RESULTS_FILENAME as BARG_RESULTS_FILENAME,
    SUMMARY_FILENAME as BARG_SUMMARY_FILENAME,
    AuditCondition,
    run_calibration_rows,
    select_bargaining_rows,
)


SCENARIO_CONFIG: dict[str, dict[str, Any]] = {
    "bargaining_opus47": {
        "family": "marble_bargaining",
        "max_turns": 36,
        "max_workers": 1,
        "kind": "bargaining",
    },
    "bidding_opus47": {
        "family": "marble_bidding",
        "max_turns": 36,
        "max_workers": 1,
        "kind": "phase5",
    },
    "swebench_workspace_opus47": {
        "family": "swebench_workspace",
        "max_turns": 90,
        "max_workers": 4,
        "kind": "phase5",
    },
    "travel_opus47": {
        "family": "travel",
        "max_turns": 36,
        "max_workers": 4,
        "kind": "phase5",
    },
}


def _slim_phase5_manifest(
    store_manifest: dict[str, Any], variant_ids: set[str]
) -> dict[str, Any]:
    """Build a slim manifest containing only ``variant_ids`` under ``main``."""
    manifest = normalize_store_manifest_for_batches(store_manifest)
    main = [
        row for row in (manifest.get("main") or [])
        if str(row.get("variant_id")) in variant_ids
    ]
    supplementary = [
        row for row in (manifest.get("supplementary") or [])
        if str(row.get("variant_id")) in variant_ids
    ]
    # Promote any supplementary matches into ``main`` so batch 2's
    # ``_select_standard`` selector reaches them. The original sweep ran
    # the rows under batch 2, so we keep the same path.
    main_total = list(main) + list(supplementary)
    out = dict(manifest)
    out["main"] = main_total
    out["supplementary"] = []
    return out


def _retry_phase5(
    *,
    scenario_dir: str,
    cfg: dict[str, Any],
    parse_error_variants: list[dict[str, Any]],
    store: Path,
    out_dir: Path,
    agent_model: str,
) -> None:
    if not parse_error_variants:
        print(f"  [{scenario_dir}] no parse-error rows, skipping")
        return
    variant_ids = {str(v["variant_id"]) for v in parse_error_variants}
    store_manifest = load_manifest(store / "manifest.json")
    slim = _slim_phase5_manifest(store_manifest, variant_ids)
    selected = slim.get("main") or []
    family = cfg["family"]
    # Defensive: filter to the requested family in case the manifest
    # carries unrelated rows under the same variant_id (it should not).
    selected = [r for r in selected if str(r.get("family_id")) == family]
    slim["main"] = selected
    if not selected:
        raise RuntimeError(
            f"[{scenario_dir}] manifest had no rows matching the parse-error "
            f"variant_ids; check retry_index.json"
        )
    print(
        f"  [{scenario_dir}] family={family} "
        f"variants_requested={len(variant_ids)} matched={len(selected)}"
    )

    # Patch batch 2's expected_rows so its selector accepts the slim count.
    spec = run_batch_for(2)
    object.__setattr__(spec, "expected_rows", len(selected))
    object.__setattr__(spec, "expected_rows_alternatives", ())

    executor = DriverOrchestratedDockerExecutor(
        store_dir=store,
        run_dir=out_dir,
        agent_model=agent_model,
        max_turns_override=cfg["max_turns"],
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    summary, _results = run_run_batch(
        manifest=slim,
        batch_number=2,
        executor=executor,
        base_dir=store,
        out_dir=out_dir,
        max_workers=int(cfg["max_workers"]),
    )
    print(
        f"  [{scenario_dir}] done: n_run={summary.n_run} "
        f"n_errors={summary.n_errors} "
        f"tsr_baseline={summary.task_success_rate_baseline} "
        f"tsr_attacker={summary.task_success_rate_attacker} "
        f"elapsed_s={summary.elapsed_seconds:.1f}"
    )


def _retry_bargaining(
    *,
    scenario_dir: str,
    cfg: dict[str, Any],
    parse_error_variants: list[dict[str, Any]],
    store: Path,
    out_dir: Path,
    agent_model: str,
) -> None:
    if not parse_error_variants:
        print(f"  [{scenario_dir}] no parse-error rows, skipping")
        return
    target_tuples = {
        (str(v["base_scenario_id"]), str(v["attack_mode"]))
        for v in parse_error_variants
    }
    base_ids = {bid for bid, _ in target_tuples}
    modes = {mode for _, mode in target_tuples}

    manifest = load_manifest(store / "manifest.json")
    # Narrow to the candidate (base_id, mode) cells, then keep only the
    # exact tuples that errored so we do not re-run already-successful rows.
    candidates = select_bargaining_rows(
        manifest, include_baseline=True, modes=modes, base_ids=base_ids,
    )
    selected = [
        row for row in candidates
        if (str(row.get("base_id")), str(row.get("attack_mode"))) in target_tuples
    ]
    if not selected:
        raise RuntimeError(
            f"[{scenario_dir}] no manifest rows matched the parse-error "
            f"(base_id, attack_mode) tuples; check retry_index.json"
        )
    print(
        f"  [{scenario_dir}] family=marble_bargaining "
        f"tuples_requested={len(target_tuples)} matched={len(selected)}"
    )

    executor = DriverOrchestratedDockerExecutor(
        store_dir=store,
        run_dir=out_dir,
        agent_model=agent_model,
        audit_condition=AuditCondition("passive"),
        simulation_attempts=1,
        max_turns_override=cfg["max_turns"],
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = run_calibration_rows(
        rows=selected,
        executor=executor,
        store_dir=store,
        out_dir=out_dir,
    )
    print(
        f"  [{scenario_dir}] done: rows_total={summary['rows_total']} "
        f"rows_errored={summary['rows_errored']} "
        f"tsr_baseline={summary['task_success_rate_baseline']} "
        f"tsr_attacker={summary['task_success_rate_attacker']} "
        f"elapsed_s={summary['elapsed_seconds']:.1f}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-run parse-error rows against a single agent model.",
    )
    parser.add_argument(
        "--run-dir", required=True, type=Path,
        help="Sweep run directory containing retry_index.json (the same dir "
             "the original sweep landed in).",
    )
    parser.add_argument(
        "--scenario", required=True,
        choices=sorted(SCENARIO_CONFIG),
        help="Which scenario block from retry_index.json to retry.",
    )
    parser.add_argument(
        "--agent-model", required=True,
        help="Bedrock model id passed to the executor.",
    )
    parser.add_argument(
        "--store", default=Path("benchmark/scenarios/v2.0.0"), type=Path,
        help="v2 store dir containing manifest.json and family folders.",
    )
    parser.add_argument(
        "--out-suffix", default="_retry",
        help="Suffix appended to <scenario_dir> to form the retry output dir.",
    )
    parser.add_argument(
        "--index-file", default="retry_index.json",
        help="Filename (relative to --run-dir) of the retry index. Override "
             "to point at a smoke variant with fewer rows.",
    )
    args = parser.parse_args()

    index_path = args.run_dir / args.index_file
    index = json.loads(index_path.read_text())
    if args.scenario not in index:
        raise SystemExit(f"scenario {args.scenario!r} not in {index_path}")
    block = index[args.scenario]
    rows = list(block.get("rows") or [])
    cfg = SCENARIO_CONFIG[args.scenario]

    out_dir = args.run_dir / f"{args.scenario}{args.out_suffix}"
    print(
        f"[retry] scenario={args.scenario} family={cfg['family']} "
        f"n_parse_errors={len(rows)} out_dir={out_dir}"
    )

    if cfg["kind"] == "phase5":
        _retry_phase5(
            scenario_dir=args.scenario,
            cfg=cfg,
            parse_error_variants=rows,
            store=args.store,
            out_dir=out_dir,
            agent_model=args.agent_model,
        )
    elif cfg["kind"] == "bargaining":
        _retry_bargaining(
            scenario_dir=args.scenario,
            cfg=cfg,
            parse_error_variants=rows,
            store=args.store,
            out_dir=out_dir,
            agent_model=args.agent_model,
        )
    else:
        raise SystemExit(f"unknown scenario kind {cfg['kind']!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
