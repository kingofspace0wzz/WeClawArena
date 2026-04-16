"""Analysis tables — headline, model comparison, rewrite-quality.

Reads the long-format CSV produced by ``aggregator.aggregate_to_csv`` and emits
pandas DataFrames plus markdown / LaTeX renderings.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def load_long_csv(csv_path: Path) -> pd.DataFrame:
    """Load the aggregated long-format CSV produced by aggregate_to_csv."""
    return pd.read_csv(csv_path)


def headline_table(df: pd.DataFrame) -> pd.DataFrame:
    """Mean + 95% normal-approx CI per condition × metric_family × metric_name.

    Returns columns: condition, metric_family, metric_name, mean, ci_low,
    ci_high, n. The CI uses a normal approximation (1.96 * sd / sqrt(n)); for
    n == 1 the CI collapses to the mean.
    """

    def agg(g: pd.DataFrame) -> pd.Series:
        n = len(g)
        m = float(g["value"].mean())
        if n <= 1:
            return pd.Series({"mean": m, "ci_low": m, "ci_high": m, "n": n})
        s = float(g["value"].std(ddof=1))
        half = 1.96 * s / np.sqrt(n)
        return pd.Series(
            {"mean": m, "ci_low": m - half, "ci_high": m + half, "n": n}
        )

    grouped = df.groupby(
        ["condition", "metric_family", "metric_name"], as_index=False
    ).apply(agg, include_groups=False)
    # Older pandas emits an extra "level_0" index column when group_keys=True;
    # drop it if present.
    if "level_0" in grouped.columns:
        grouped = grouped.drop(columns=["level_0"])
    return grouped.reset_index(drop=True)


def model_comparison_table(
    df: pd.DataFrame, *, condition: str = "passive"
) -> pd.DataFrame:
    """SAF overall + per-dim per model, single condition."""
    sub = df[(df["condition"] == condition) & (df["metric_family"] == "saf")]
    pivot = (
        sub.groupby(["model", "metric_name"])["value"].mean().unstack("metric_name")
    )
    return pivot.reset_index()


def rewrite_quality_table(df: pd.DataFrame) -> pd.DataFrame:
    """TSR per scenario per condition, with delta_enforce_minus_passive if both exist."""
    tsr = df[(df["metric_family"] == "task") & (df["metric_name"] == "tsr")]
    pivot = tsr.pivot_table(
        index="scenario_id", columns="condition", values="value", aggfunc="mean"
    )
    if "enforce" in pivot.columns and "passive" in pivot.columns:
        pivot["delta_enforce_minus_passive"] = pivot["enforce"] - pivot["passive"]
    return pivot.reset_index()


def to_markdown(df: pd.DataFrame) -> str:
    """Render a DataFrame as a GitHub-flavoured markdown table (3-digit floats)."""
    return df.to_markdown(index=False, floatfmt=".3f")


def to_latex(df: pd.DataFrame) -> str:
    """Render a DataFrame as a LaTeX ``tabular`` fragment (3-digit floats)."""
    return df.to_latex(index=False, float_format="%.3f")
