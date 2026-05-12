from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from clawsocialarena.gateway.compose_runner import docker_available
from clawsocialarena.llm.openai_client import require_openai_key
from clawsocialarena.simulation.condition_sentinel import (
    run_condition_sentinel_batch,
    write_condition_sentinel_report,
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Rerun accepted naturalized batch rows under audit-condition "
            "sentinel settings."
        )
    )
    parser.add_argument("--source-batch-dir", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--out", type=Path, default=Path("benchmark/batches"))
    parser.add_argument("--scenario-id", action="append", default=[])
    parser.add_argument("--scenario-ids-file", type=Path)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--condition",
        action="append",
        choices=("baseline", "passive", "enforce"),
        default=[],
        help=(
            "Audit condition to run. May be repeated. Defaults to all three "
            "conditions."
        ),
    )
    parser.add_argument("--construction-model")
    parser.add_argument("--agent-model")
    parser.add_argument("--rerun-existing", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.limit <= 0:
        print("--limit must be positive", file=sys.stderr)
        return 2
    scenario_ids = _scenario_ids_from_args(args)
    try:
        require_openai_key()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not docker_available():
        print("docker is required for condition sentinel runs", file=sys.stderr)
        return 2
    report = run_condition_sentinel_batch(
        source_batch_dir=args.source_batch_dir,
        batch_id=args.batch_id,
        out_dir=args.out,
        scenario_ids=scenario_ids,
        conditions=args.condition or None,
        limit=args.limit,
        construction_model=args.construction_model,
        agent_model=args.agent_model,
        rerun_existing=args.rerun_existing,
    )
    report_path = write_condition_sentinel_report(report, args.out / args.batch_id)
    print(
        json.dumps(
            {
                "batch_report": str(report_path),
                "accepted": report.accepted_count,
                "failed": report.failed_count,
                "condition_counts": report.condition_counts,
            },
            sort_keys=True,
        )
    )
    return 0


def _scenario_ids_from_args(args: argparse.Namespace) -> list[str] | None:
    scenario_ids = list(args.scenario_id or [])
    if args.scenario_ids_file is not None:
        scenario_ids.extend(
            line.strip()
            for line in args.scenario_ids_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    if not scenario_ids:
        return None
    return list(dict.fromkeys(scenario_ids))


if __name__ == "__main__":
    raise SystemExit(main())
