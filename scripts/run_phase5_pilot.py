"""CLI driver for the Phase-5 pilot orchestrator (S4 step 5).

Two subcommands:

- ``run-batch``: execute one batch (1..5) against a previously
  generated manifest, write the per-batch report + JSONL results.
- ``aggregate``: combine all five per-batch reports into the final
  ``PILOT_REPORT.json`` + ``PILOT_REPORT.md``.

The ``--executor`` flag selects the scenario executor:

- ``mock``: deterministic mock (used by smoke tests of the
  orchestrator scaffold; no LLM calls).
- ``live``: gpt-5.2 naturalization + gpt-4.1-mini agent simulation.
  Wired by Run-Batches 1..5; calling this before Run-Batch 1 lands
  raises ``NotImplementedError``.

Examples:

    # Run only the smoke batch with the mock executor (CI-safe):
    python scripts/run_phase5_pilot.py run-batch \\
        --manifest benchmark/phase5/scaffold/phase5_manifest.json \\
        --base-dir benchmark/phase5/scaffold \\
        --out-dir benchmark/phase5/pilot \\
        --batch 1 --executor mock

    # Aggregate all five batches into PILOT_REPORT.json + .md:
    python scripts/run_phase5_pilot.py aggregate \\
        --out-dir benchmark/phase5/pilot
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from clawsocialarena.generator.phase5_manifest import load_manifest  # noqa: E402
from clawsocialarena.orchestrator.phase5_executor import (  # noqa: E402
    MockScenarioExecutor,
    ScenarioExecutor,
)
from clawsocialarena.orchestrator.phase5_docker_executor import (  # noqa: E402
    DriverOrchestratedDockerExecutor,
)
from clawsocialarena.orchestrator.phase5_live_executor import (  # noqa: E402
    LiveScenarioExecutor,
    PHASE5_DEFAULT_AGENT_MODEL,
    PHASE5_DEFAULT_MAX_TURNS,
    PHASE5_DEFAULT_NATURALIZATION_MODEL,
)
from clawsocialarena.orchestrator.phase5_orchestrator import (  # noqa: E402
    PHASE5_BATCH_REPORT_FILENAME_TEMPLATE,
    PHASE5_DEFAULT_MAX_WORKERS,
    PHASE5_RUN_BATCHES,
    RunBatchSummary,
    aggregate_pilot_report,
    run_run_batch,
)

_FILTER_KEY_TO_ROW_FIELD = {
    "family": "family_id",
    "cell": "cell_id",
    "task": "task_index",
    "mode": "attack_mode",
    "base_id": "base_id",
}


def parse_filter_string(spec: str) -> dict[str, str]:
    """Parse ``key=value[,key=value...]`` into a dict; empty -> {}.

    Raises ValueError on unknown keys.
    """
    spec = (spec or "").strip()
    if not spec:
        return {}
    out: dict[str, str] = {}
    for pair in spec.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise ValueError(f"filter spec missing '=' in {pair!r}")
        k, v = pair.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k not in _FILTER_KEY_TO_ROW_FIELD:
            raise ValueError(f"unknown filter key {k!r}; "
                             f"valid: {sorted(_FILTER_KEY_TO_ROW_FIELD)}")
        out[k] = v
    return out


def apply_filter(rows: list[dict], flt: dict[str, str]) -> list[dict]:
    """Return rows that match every (filter_key, filter_value) pair."""
    if not flt:
        return list(rows)
    out: list[dict] = []
    for row in rows:
        keep = True
        for k, v in flt.items():
            field = _FILTER_KEY_TO_ROW_FIELD[k]
            if str(row.get(field)) != str(v):
                keep = False
                break
        if keep:
            out.append(row)
    return out


def _truncate_manifest_for_limit(
    *, manifest: dict, batch_number: int, limit: int
) -> dict:
    """Trim the manifest so that the named batch's selector lands on
    exactly ``limit`` rows. The total expected count is also relaxed
    so RunBatchSpec.select() does not raise.

    Used by ``--limit`` to do small live validations before paying
    the full batch cost. Accepts an input manifest that is already
    pre-trimmed (e.g., a hand-built smoke manifest with only a few
    rows): we relax ``expected_rows`` to the manifest's own count
    BEFORE walking the selector so the assertion does not fire
    while we are trying to enumerate the rows.
    """
    from clawsocialarena.orchestrator.phase5_run_batches import run_batch_for

    spec = run_batch_for(batch_number)
    # Relax expected_rows up front so spec.select() does not assert
    # against the full pilot's expected count when the caller hands
    # us a pre-trimmed manifest.
    pre_trim_count = len(manifest.get("main", [])) + len(
        manifest.get("supplementary", [])
    )
    object.__setattr__(
        spec, "expected_rows", min(pre_trim_count, spec.expected_rows)
    )
    full_rows = spec.select(manifest)
    keep = full_rows[:limit]
    keep_ids = {row["variant_id"] for row in keep}

    new_manifest = dict(manifest)
    new_manifest["main"] = [
        row for row in manifest.get("main", []) if row["variant_id"] in keep_ids
    ]
    new_manifest["supplementary"] = [
        row
        for row in manifest.get("supplementary", [])
        if row["variant_id"] in keep_ids
    ]
    # Lock the final expected_rows to the trimmed slice count.
    object.__setattr__(spec, "expected_rows", len(keep))
    return new_manifest


def _select_executor(args: argparse.Namespace) -> ScenarioExecutor:
    if args.executor == "mock":
        return MockScenarioExecutor(seed=args.mock_seed)
    if args.executor == "docker":
        store = getattr(args, "store", None)
        if store is None:
            raise ValueError("--executor docker requires --store")
        return DriverOrchestratedDockerExecutor(
            store_dir=store,
            run_dir=args.out_dir,
            agent_model=args.agent_model,
            max_turns_override=args.max_turns,
        )
    if args.executor == "live":
        mode = _resolve_live_mode(args)
        store = getattr(args, "store", None)
        out_dir = getattr(args, "out_dir", None)
        executor = LiveScenarioExecutor(
            naturalization_model=args.naturalization_model,
            agent_model=args.agent_model,
            max_turns=args.max_turns,
            mode=mode,
            store_dir=store,
            run_dir=out_dir if store is not None else None,
        )
        return executor
    raise ValueError(f"unknown --executor={args.executor!r}")


def _resolve_live_mode(args: argparse.Namespace) -> str:
    """Pick the live executor's mode.

    ``--mode auto`` (default) maps batch 1 to ``naturalization_only``
    (R-B 1's smoke contract) and every later batch to ``full`` (the
    R-B 2..5 contract requiring agent-loop + scoring). ``--mode
    naturalization_only`` / ``--mode full`` force the corresponding
    branch regardless of batch number.
    """
    explicit = getattr(args, "mode", "auto")
    if explicit == "naturalization_only":
        return "naturalization_only"
    if explicit == "full":
        return "full"
    if explicit != "auto":
        raise ValueError(f"unknown --mode={explicit!r}")
    return "naturalization_only" if args.batch == 1 else "full"


def _apply_filter_to_manifest(manifest: dict, filter_spec: str) -> dict:
    """Return a shallow-copied manifest with rows narrowed by filter_spec.

    Works for both legacy manifests (keys 'main'/'supplementary') and
    v2 store manifests (key 'rows'). When filter_spec is empty, returns
    the manifest unchanged.
    """
    flt = parse_filter_string(filter_spec)
    if not flt:
        return manifest
    out = dict(manifest)
    for key in ("main", "supplementary", "rows"):
        if key in out:
            out[key] = apply_filter(out[key], flt)
    return out


def _relax_batch_expected_rows_for_filtered_manifest(
    *,
    manifest: dict,
    batch_number: int,
) -> None:
    from clawsocialarena.orchestrator.phase5_run_batches import run_batch_for

    spec = run_batch_for(batch_number)
    rows = spec.selector_fn(manifest)
    object.__setattr__(spec, "expected_rows", len(rows))


def _load_manifest_for_batches(
    *, manifest_path: Path, store: Path | None
) -> dict[str, Any]:
    source = store / "manifest.json" if store is not None else manifest_path
    return normalize_store_manifest_for_batches(load_manifest(source))


def _cmd_run_batch(args: argparse.Namespace) -> int:
    store: Path | None = getattr(args, "store", None)
    manifest = _load_manifest_for_batches(
        manifest_path=args.manifest,
        store=store,
    )
    filter_spec: str = getattr(args, "filter", "")
    if filter_spec:
        manifest = _apply_filter_to_manifest(manifest, filter_spec)
        if args.limit is None or args.limit <= 0:
            _relax_batch_expected_rows_for_filtered_manifest(
                manifest=manifest,
                batch_number=args.batch,
            )
    if args.limit is not None and args.limit > 0:
        # Truncate the batch's slice in-place so we can do a small live
        # validation before committing to a full batch's cost. The
        # batch's selector still asserts its full expected_rows, so we
        # override it via a synthetic 'main' list trimmed to the
        # batch's slice ∩ first <limit> rows.
        manifest = _truncate_manifest_for_limit(
            manifest=manifest, batch_number=args.batch, limit=args.limit
        )
    executor = _select_executor(args)
    summary, _results = run_run_batch(
        manifest=manifest,
        batch_number=args.batch,
        executor=executor,
        base_dir=args.base_dir,
        out_dir=args.out_dir,
        max_workers=args.max_workers,
    )
    if not args.quiet:
        print(
            json.dumps(
                {
                    "phase5_run_batch": summary.batch_number,
                    "name": summary.name,
                    "n_run": summary.n_run,
                    "n_errors": summary.n_errors,
                    "task_success_rate_baseline": (
                        summary.task_success_rate_baseline
                    ),
                    "task_success_rate_attacker": (
                        summary.task_success_rate_attacker
                    ),
                    "attack_success_rate": summary.attack_success_rate,
                    "elapsed_seconds": summary.elapsed_seconds,
                },
                indent=2,
            )
        )
    return 0


def _cmd_aggregate(args: argparse.Namespace) -> int:
    out_dir: Path = args.out_dir
    summaries: list[RunBatchSummary] = []
    for spec in PHASE5_RUN_BATCHES:
        report_path = out_dir / PHASE5_BATCH_REPORT_FILENAME_TEMPLATE.format(
            batch=spec.batch_number, name=spec.name
        )
        if not report_path.is_file():
            raise FileNotFoundError(
                f"missing per-batch report for batch {spec.batch_number} "
                f"at {report_path}; run-batch must run before aggregate"
            )
        data = json.loads(report_path.read_text(encoding="utf-8"))
        summaries.append(RunBatchSummary(**data))
    payload = aggregate_pilot_report(out_dir=out_dir, batch_summaries=summaries)
    if not args.quiet:
        # Just the headline numbers; the full payload is on disk.
        print(
            json.dumps(
                {
                    "expected_total_rows": payload["expected_total_rows"],
                    "total_rows_run": payload["total_rows_run"],
                    "total_errors": payload["total_errors"],
                    "naturalization_total_tokens": (
                        payload["naturalization_total_tokens"]
                    ),
                    "simulation_total_tokens": payload[
                        "simulation_total_tokens"
                    ],
                },
                indent=2,
            )
        )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run-batch", help="Run one batch (1..5).")
    run.add_argument("--manifest", required=True, type=Path)
    run.add_argument("--base-dir", required=True, type=Path)
    run.add_argument("--out-dir", required=True, type=Path)
    run.add_argument("--batch", required=True, type=int, choices=(1, 2, 3, 4, 5))
    run.add_argument("--executor", choices=("mock", "live", "docker"), default="mock")
    run.add_argument(
        "--naturalization-model",
        default=PHASE5_DEFAULT_NATURALIZATION_MODEL,
        help="Naturalization model id for the live executor.",
    )
    run.add_argument(
        "--agent-model",
        default=PHASE5_DEFAULT_AGENT_MODEL,
        help="Per-agent model id for the live executor.",
    )
    run.add_argument(
        "--max-turns", type=int, default=PHASE5_DEFAULT_MAX_TURNS
    )
    run.add_argument(
        "--max-workers",
        type=int,
        default=PHASE5_DEFAULT_MAX_WORKERS,
        help=(
            "Maximum concurrent scenario rows for this batch. Use 1 for "
            "Docker sweeps when shared image builds must be serialized."
        ),
    )
    run.add_argument(
        "--mode",
        choices=("auto", "naturalization_only", "full"),
        default="auto",
        help=(
            "Live executor mode. 'auto' maps batch 1 -> "
            "naturalization_only and batches 2..5 -> full. 'full' "
            "wires the agent loop + env_assertion + attack + SAF "
            "scoring. 'naturalization_only' replicates R-B 1's smoke "
            "contract regardless of batch number."
        ),
    )
    run.add_argument("--mock-seed", type=int, default=0)
    run.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Process only the first N rows of the batch's slice. Useful "
            "for live-LLM smoke validation before spending the full "
            "batch budget. The batch's expected_rows assertion is "
            "temporarily relaxed for the truncated run."
        ),
    )
    run.add_argument("--quiet", action="store_true")
    run.add_argument(
        "--store",
        type=Path,
        default=None,
        help=(
            "Path to the v2 naturalized-scenarios store. "
            "When set, live executor reads from here."
        ),
    )
    run.add_argument(
        "--filter",
        default="",
        help=(
            "key=value[,key=value...] (keys: family, cell, "
            "task, mode, base_id). ANDed with --batch."
        ),
    )
    run.set_defaults(func=_cmd_run_batch)

    agg = sub.add_parser(
        "aggregate", help="Aggregate all five per-batch reports."
    )
    agg.add_argument("--out-dir", required=True, type=Path)
    agg.add_argument("--quiet", action="store_true")
    agg.set_defaults(func=_cmd_aggregate)

    return parser


def normalize_store_manifest_for_batches(manifest: dict[str, Any]) -> dict[str, Any]:
    """Expose a v2 store manifest's ``rows`` list as run-batch ``main`` rows."""
    if "rows" not in manifest or "main" in manifest:
        return manifest
    out = dict(manifest)
    out["main"] = list(manifest.get("rows") or [])
    out["supplementary"] = list(manifest.get("supplementary") or [])
    return out


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
