"""Unified analysis CLI.

Usage:
    python -m clawsocialarena.analysis aggregate --root results/v1 --out results/v1/long.csv
    python -m clawsocialarena.analysis table --csv results/v1/long.csv --kind headline --out results/v1/headline.md
    python -m clawsocialarena.analysis prereg --csv results/v1/long.csv --out results/v1/prereg.md
"""

from __future__ import annotations

import argparse
from pathlib import Path

from clawsocialarena.analysis.aggregator import aggregate_to_csv
from clawsocialarena.analysis.prereg_check import reconcile, render_report
from clawsocialarena.analysis.tables import (
    headline_table,
    load_long_csv,
    model_comparison_table,
    rewrite_quality_table,
    to_latex,
    to_markdown,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="clawsocialarena.analysis")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("aggregate", help="Aggregate scorecard JSONs to CSV.")
    a.add_argument("--root", type=Path, required=True)
    a.add_argument("--out", type=Path, required=True)
    a.add_argument(
        "--format",
        choices=["wide", "long"],
        default="wide",
        help="wide (default, Phase H): one row per scorecard. "
        "long (legacy): one row per (family, name, value) triple.",
    )

    t = sub.add_parser("table", help="Emit a markdown or LaTeX summary table.")
    t.add_argument("--csv", type=Path, required=True)
    t.add_argument(
        "--kind", choices=["headline", "model", "rewrite"], required=True
    )
    t.add_argument("--condition", default="passive", help="for model-comparison table")
    t.add_argument("--format", choices=["md", "latex"], default="md")
    t.add_argument("--out", type=Path)

    pr = sub.add_parser(
        "prereg", help="Reconcile aggregated results against the pre-registration."
    )
    pr.add_argument("--csv", type=Path, required=True)
    pr.add_argument("--out", type=Path, required=True)

    args = p.parse_args(argv)

    if args.cmd == "aggregate":
        n = aggregate_to_csv(args.root, args.out, wide=(args.format == "wide"))
        print(f"Wrote {n} rows to {args.out}")
        return 0

    if args.cmd == "table":
        df = load_long_csv(args.csv)
        if args.kind == "headline":
            out = headline_table(df)
        elif args.kind == "model":
            out = model_comparison_table(df, condition=args.condition)
        else:
            out = rewrite_quality_table(df)
        rendered = to_latex(out) if args.format == "latex" else to_markdown(out)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(rendered)
            print(f"Wrote {args.out}")
        else:
            print(rendered)
        return 0

    if args.cmd == "prereg":
        results = reconcile(args.csv)
        report = render_report(results)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report)
        print(f"Wrote {args.out}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
