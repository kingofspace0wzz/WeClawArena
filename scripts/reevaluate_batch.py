from __future__ import annotations

import argparse
import json
from pathlib import Path

from clawsocialarena.simulation.reevaluate import reevaluate_existing_batch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-evaluate an existing benchmark batch from frozen artifacts.",
    )
    parser.add_argument("--batch-dir", type=Path, required=True)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Report output path. Defaults to "
            "<batch-dir>/reevaluated_batch_report.json."
        ),
    )
    parser.add_argument(
        "--recompute-scorecards",
        action="store_true",
        help=(
            "Recompute each run_scorecard.json from persisted logs before "
            "rebuilding the batch report."
        ),
    )
    parser.add_argument(
        "--agent-model",
        default=None,
        help="Override the model label written into recomputed scorecard metadata.",
    )
    args = parser.parse_args(argv)

    report = reevaluate_existing_batch(
        batch_dir=args.batch_dir,
        recompute_scorecards=args.recompute_scorecards,
        agent_model=args.agent_model,
    )
    out = args.out or args.batch_dir / "reevaluated_batch_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {out} "
        f"(accepted={report.accepted_count}, failed={report.failed_count})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

