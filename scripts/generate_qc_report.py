from __future__ import annotations

import argparse
import sys
from pathlib import Path

from clawsocialarena.simulation.qc_report import GateDecision, write_qc_report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a construction QC Markdown report for one batch."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--batch-dir", type=Path)
    source.add_argument("--batch-report", type=Path)
    parser.add_argument("--review-feedback", type=Path)
    parser.add_argument(
        "--gate-decision",
        choices=("proceed", "re_score", "regenerate_rows", "stop_scale_out"),
    )
    parser.add_argument("--next-batch-command")
    parser.add_argument("--out", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    batch_report_path = (
        args.batch_report
        if args.batch_report is not None
        else args.batch_dir / "batch_report.json"
    )
    if not batch_report_path.exists():
        print(f"missing batch report: {batch_report_path}", file=sys.stderr)
        return 2
    if args.review_feedback is not None and not args.review_feedback.exists():
        print(f"missing review feedback: {args.review_feedback}", file=sys.stderr)
        return 2
    output_path = write_qc_report(
        batch_report_path=batch_report_path,
        review_feedback_path=args.review_feedback,
        output_path=args.out,
        gate_decision=_gate_decision(args.gate_decision),
        next_batch_command=args.next_batch_command,
    )
    print(output_path)
    return 0


def _gate_decision(value: str | None) -> GateDecision | None:
    if value is None:
        return None
    return value  # type: ignore[return-value]


if __name__ == "__main__":
    raise SystemExit(main())
