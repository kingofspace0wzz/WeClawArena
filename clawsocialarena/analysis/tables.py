"""Analysis tables — headline, model comparison, rewrite quality.

Every table producer operates on the wide CSV written by
:func:`clawsocialarena.analysis.aggregator.aggregate_to_csv` (one row per
scorecard, columns enumerated by :data:`aggregator.WIDE_FIELDS`) and
returns a ``(markdown, latex)`` pair of rendered strings.

Every output carries a ``live_or_replay`` label so live vs. replay cells
can be distinguished in the final paper tables. For headline rows, the
label groups into the group-by keys; for model-comparison and
rewrite-quality summaries the label is emitted as a stratification
column.

Legacy Phase-6 callers consumed the long-format CSV with
``metric_family``/``metric_name``/``value`` columns; the
:func:`load_long_csv` helper still reads both shapes, so the old signature
(return a :class:`~pandas.DataFrame`) is preserved in the thin wrappers
:func:`headline_table_df`, :func:`model_comparison_table_df`, and
:func:`rewrite_quality_table_df`. The new Phase H signatures are the
plain ``*_table`` functions that return ``(md, latex)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


# ---- CSV loader shared with Phase 6 prereg paths -----------------------------------

def load_long_csv(csv_path: Path) -> pd.DataFrame:
    """Load an aggregator CSV (either wide or legacy long format)."""
    return pd.read_csv(csv_path)


# ---- Headline ---------------------------------------------------------------------

# Metric families used in the headline table; entries cover SAF overall,
# task success, privacy leak, security ASR, and governance violation rate.
_HEADLINE_METRICS: tuple[str, ...] = (
    "saf_overall",
    "tsr",
    "asr",
    "cdlr",
    "mplr",
    "governance_violation_rate",
)


def _mean_ci(series: pd.Series, *, z: float = 1.96) -> dict[str, float]:
    """Normal-approximation 95% CI for the mean of a numeric series."""

    n = int(series.count())
    m = float(series.mean()) if n > 0 else float("nan")
    if n <= 1:
        return {"mean": m, "ci_low": m, "ci_high": m, "n": n}
    s = float(series.std(ddof=1))
    half = z * s / np.sqrt(n)
    return {"mean": m, "ci_low": m - half, "ci_high": m + half, "n": n}


def _ensure_wide(df: pd.DataFrame) -> pd.DataFrame:
    """Raise if ``df`` is not wide; add I6 fallback columns when absent."""

    missing = {"scenario_id", "condition", "model", "category"} - set(df.columns)
    if missing:
        raise ValueError(
            f"expected wide-format CSV, missing columns: {sorted(missing)}"
        )
    if "live_or_replay" not in df.columns:
        df = df.assign(live_or_replay="live")
    if "attack_axis" not in df.columns:
        df = df.assign(attack_axis=df["category"])
    if "attack_type" not in df.columns:
        df = df.assign(attack_type="")
    return df


def headline_table_df(df: pd.DataFrame) -> pd.DataFrame:
    """Headline table as a DataFrame: condition × attack axis × metric."""

    df = _ensure_wide(df)
    rows: list[dict] = []
    for (cond, attack_axis, lor), sub in df.groupby(
        ["condition", "attack_axis", "live_or_replay"], dropna=False
    ):
        for metric in _HEADLINE_METRICS:
            if metric not in sub.columns:
                continue
            ci = _mean_ci(sub[metric].astype(float))
            rows.append(
                {
                    "condition": cond,
                    "attack_axis": attack_axis,
                    "live_or_replay": lor,
                    "metric": metric,
                    **ci,
                }
            )
    out = pd.DataFrame(rows)
    # Stable sort so markdown/LaTeX rendering is deterministic.
    if not out.empty:
        out = out.sort_values(
            ["attack_axis", "metric", "condition", "live_or_replay"]
        ).reset_index(drop=True)
    return out


def headline_table(df: pd.DataFrame) -> tuple[str, str]:
    """Return ``(markdown, latex)`` renderings of the headline table."""

    return _render_pair(headline_table_df(df))


# ---- Model comparison -------------------------------------------------------------

# SAF dimensions reported in the model table.
_SAF_DIM_COLUMNS: tuple[str, ...] = (
    "saf_overall",
    "recoverability",
    "policy_checkability",
    "attribution",
    "evidence_integrity",
    "phase_scoped_policy",
    "identity_governance",
    "psi",
    "tau",
    "sigma",
    "phi",
    "gamma",
)


def model_comparison_table_df(
    df: pd.DataFrame, *, condition: str = "passive"
) -> pd.DataFrame:
    """SAF (overall + per-dim) per model × attack axis, single condition."""

    df = _ensure_wide(df)
    sub = df[df["condition"] == condition]
    if sub.empty:
        return pd.DataFrame(
            columns=["model", "attack_axis", "live_or_replay", *_SAF_DIM_COLUMNS]
        )
    present_dims = [col for col in _SAF_DIM_COLUMNS if col in sub.columns]
    grouped = (
        sub.groupby(["model", "attack_axis", "live_or_replay"], dropna=False)[
            present_dims
        ]
        .mean()
        .reset_index()
    )
    return grouped.sort_values(
        ["attack_axis", "model", "live_or_replay"]
    ).reset_index(drop=True)


def model_comparison_table(
    df: pd.DataFrame, *, condition: str = "passive"
) -> tuple[str, str]:
    """Return ``(markdown, latex)`` renderings of the model-comparison table."""

    return _render_pair(model_comparison_table_df(df, condition=condition))


# ---- Rewrite quality --------------------------------------------------------------

def rewrite_quality_table_df(df: pd.DataFrame) -> pd.DataFrame:
    """``TSR(enforce) − TSR(passive)`` per attack axis with 95% CI."""

    df = _ensure_wide(df)
    sub = df[df["condition"].isin(["passive", "enforce"])].copy()
    # Pair by (attack_axis, model, scenario_id, live_or_replay) then diff.
    pivot = sub.pivot_table(
        index=["attack_axis", "model", "scenario_id", "live_or_replay"],
        columns="condition",
        values="tsr",
        aggfunc="mean",
    )
    if not {"passive", "enforce"} <= set(pivot.columns):
        # Not enough conditions present; return an empty but shaped frame.
        return pd.DataFrame(
            columns=[
                "attack_axis",
                "live_or_replay",
                "delta_mean",
                "ci_low",
                "ci_high",
                "n",
            ]
        )
    pivot["delta"] = pivot["enforce"] - pivot["passive"]
    pivot = pivot.reset_index()
    rows: list[dict] = []
    for (attack_axis, lor), bucket in pivot.groupby(
        ["attack_axis", "live_or_replay"], dropna=False
    ):
        ci = _mean_ci(bucket["delta"].astype(float))
        rows.append(
            {
                "attack_axis": attack_axis,
                "live_or_replay": lor,
                "delta_mean": ci["mean"],
                "ci_low": ci["ci_low"],
                "ci_high": ci["ci_high"],
                "n": ci["n"],
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["attack_axis", "live_or_replay"]
    ).reset_index(drop=True)


def rewrite_quality_table(df: pd.DataFrame) -> tuple[str, str]:
    """Return ``(markdown, latex)`` renderings of the rewrite-quality table."""

    return _render_pair(rewrite_quality_table_df(df))


# ---- Rendering helpers ------------------------------------------------------------

def to_markdown(df: pd.DataFrame) -> str:
    """Render a DataFrame as a GitHub-flavoured markdown table (3-digit floats)."""

    if df.empty:
        return "(empty table)"
    return df.to_markdown(index=False, floatfmt=".3f")


def to_latex(df: pd.DataFrame) -> str:
    """Render a DataFrame as a LaTeX ``tabular`` fragment (3-digit floats)."""

    if df.empty:
        return "% empty table"
    return df.to_latex(index=False, float_format="%.3f")


def _render_pair(df: pd.DataFrame) -> tuple[str, str]:
    return to_markdown(df), to_latex(df)


# ---- Back-compat shims for Phase 6 long-format callers ----------------------------

@dataclass
class _LongMetricRef:
    family: str
    name: str


def headline_table_long(df: pd.DataFrame) -> pd.DataFrame:
    """Legacy long-format headline table (one row per (condition, family, name))."""

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
    if "level_0" in grouped.columns:
        grouped = grouped.drop(columns=["level_0"])
    return grouped.reset_index(drop=True)


def model_comparison_table_long(
    df: pd.DataFrame, *, condition: str = "passive"
) -> pd.DataFrame:
    """Legacy long-format model-comparison pivot."""

    sub = df[(df["condition"] == condition) & (df["metric_family"] == "saf")]
    pivot = (
        sub.groupby(["model", "metric_name"])["value"]
        .mean()
        .unstack("metric_name")
    )
    return pivot.reset_index()


def rewrite_quality_table_long(df: pd.DataFrame) -> pd.DataFrame:
    """Legacy long-format rewrite-quality pivot."""

    tsr = df[(df["metric_family"] == "task") & (df["metric_name"] == "tsr")]
    pivot = tsr.pivot_table(
        index="scenario_id", columns="condition", values="value", aggfunc="mean"
    )
    if "enforce" in pivot.columns and "passive" in pivot.columns:
        pivot["delta_enforce_minus_passive"] = pivot["enforce"] - pivot["passive"]
    return pivot.reset_index()


def _is_long_format(df: pd.DataFrame) -> bool:
    """Heuristic: treat a frame as long-format if it carries the Phase-6 triple."""

    return {"metric_family", "metric_name", "value"} <= set(df.columns)


def _dispatch_table(wide_fn, long_fn):
    """Wrap a Phase H wide-format function so legacy callers still work."""

    def _wrapped(df: pd.DataFrame, **kwargs):  # type: ignore[no-untyped-def]
        if _is_long_format(df):
            return long_fn(df, **kwargs)
        return wide_fn(df, **kwargs)

    return _wrapped


# Backwards-compatible callables: transparent dispatch on CSV shape.
headline_table_legacy = _dispatch_table(headline_table_df, headline_table_long)
model_comparison_table_legacy = _dispatch_table(
    model_comparison_table_df, model_comparison_table_long
)
rewrite_quality_table_legacy = _dispatch_table(
    rewrite_quality_table_df, rewrite_quality_table_long
)
