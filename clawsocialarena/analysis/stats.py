"""Statistical tests for Phase H.

The Phase H version operates on the wide CSV produced by
:func:`clawsocialarena.analysis.aggregator.aggregate_to_csv`. Each
producer returns a typed :class:`StatTestResult` dataclass so callers
can check ``result.significant`` without re-parsing floats.

Public surface:

- :func:`wilcoxon_paired` — paired Wilcoxon signed-rank test on the
  metric difference between two conditions on matched scenarios.
- :func:`kruskal_wallis` — non-parametric H-test across groups defined
  by a column in the wide DataFrame.
- :func:`bonferroni_correct` — multiple-comparison correction.
- :func:`saf_threshold_sensitivity` — Phase H6 sensitivity helper
  reporting binary SAF pass rates at a swept threshold.

Phase-6 back-compat wrappers ``paired_wilcoxon``, ``kruskal_categories``,
and ``bonferroni`` keep their long-format dict signatures so existing
tests remain green.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import pandas as pd
from scipy import stats


ALPHA_DEFAULT = 0.05


@dataclass(frozen=True)
class StatTestResult:
    """Typed result returned by the Phase H statistical tests.

    Attributes:
        statistic: The test statistic (Wilcoxon W, Kruskal H, etc.).
        pvalue: Two-sided p-value. ``NaN`` when the test could not be
            computed (e.g., fewer than two samples).
        significant: ``True`` iff ``pvalue`` is defined and below
            ``alpha``. The default alpha is 0.05.
        n: Sample size the test was computed on (paired n for Wilcoxon,
            total n for Kruskal).
        extra: Free-form diagnostic dict (e.g., per-group sizes for
            Kruskal-Wallis). Never consumed by the ``significant`` flag.
    """

    statistic: float
    pvalue: float
    significant: bool
    n: int = 0
    extra: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # Dataclasses disallow mutable defaults; hand-init the dict here.
        if self.extra is None:
            object.__setattr__(self, "extra", {})


def _from(stat: float, p: float, n: int, *, alpha: float = ALPHA_DEFAULT, extra: dict | None = None) -> StatTestResult:
    """Build a :class:`StatTestResult` with deterministic significance handling."""

    sig = (not math.isnan(p)) and (p < alpha)
    return StatTestResult(statistic=float(stat), pvalue=float(p), significant=sig, n=int(n), extra=dict(extra or {}))


# ---- Wilcoxon ---------------------------------------------------------------

def wilcoxon_paired(
    df: pd.DataFrame,
    *,
    metric: str,
    conditions: tuple[str, str],
    pair_keys: Sequence[str] = ("scenario_id", "model"),
    alpha: float = ALPHA_DEFAULT,
) -> StatTestResult:
    """Paired Wilcoxon signed-rank between ``conditions[0]`` and ``conditions[1]``.

    Arguments:
        df: Wide DataFrame with at least the columns in ``pair_keys``,
            ``condition``, and ``metric``.
        metric: Column name (e.g., ``"tsr"`` or ``"saf_overall"``).
        conditions: Two condition labels (e.g., ``("baseline", "enforce")``).
        pair_keys: Columns used to pair observations across conditions.
            Default: match by scenario + model.
        alpha: Significance threshold for ``significant``.

    Returns a :class:`StatTestResult`. When fewer than two matched
    pairs exist, returns ``pvalue=nan``. When all paired differences
    are zero, returns ``statistic=0`` + ``pvalue=1`` (no shift).
    """

    a_label, b_label = conditions
    sub = df[df["condition"].isin(conditions)]
    if sub.empty or metric not in sub.columns:
        return _from(math.nan, math.nan, 0, alpha=alpha)

    a = sub[sub["condition"] == a_label].groupby(list(pair_keys))[metric].mean()
    b = sub[sub["condition"] == b_label].groupby(list(pair_keys))[metric].mean()
    paired = pd.concat([a, b], axis=1, keys=[a_label, b_label]).dropna()
    n = int(len(paired))
    if n < 2:
        return _from(math.nan, math.nan, n, alpha=alpha)

    diffs = paired[b_label] - paired[a_label]
    if (diffs == 0).all():
        return _from(0.0, 1.0, n, alpha=alpha)

    w = stats.wilcoxon(paired[a_label], paired[b_label])
    return _from(float(w.statistic), float(w.pvalue), n, alpha=alpha)


# ---- Kruskal-Wallis ---------------------------------------------------------

def kruskal_wallis(
    df: pd.DataFrame,
    *,
    metric: str,
    group_col: str,
    condition: str | None = None,
    alpha: float = ALPHA_DEFAULT,
) -> StatTestResult:
    """Kruskal-Wallis H-test across groups defined by ``group_col``.

    Arguments:
        df: Wide DataFrame.
        metric: Numeric column to compare across groups.
        group_col: Column whose distinct values define the groups
            (``"category"``, ``"model"`` are the natural choices).
        condition: If provided, filter rows to this condition before
            grouping (e.g., hold at ``"passive"``).
        alpha: Significance threshold.

    Returns a :class:`StatTestResult` whose ``extra`` dict carries the
    per-group sample sizes. When fewer than two groups are present,
    returns ``pvalue=nan``.
    """

    sub = df if condition is None else df[df["condition"] == condition]
    if sub.empty or metric not in sub.columns or group_col not in sub.columns:
        return _from(math.nan, math.nan, 0, alpha=alpha)

    groups: list[list[float]] = []
    sizes: dict[str, int] = {}
    for key, chunk in sub.groupby(group_col, dropna=False):
        values = chunk[metric].dropna().to_numpy().tolist()
        if values:
            groups.append(values)
            sizes[str(key)] = len(values)
    n = sum(len(g) for g in groups)
    if len(groups) < 2:
        return _from(math.nan, math.nan, n, alpha=alpha, extra={"group_sizes": sizes})
    h = stats.kruskal(*groups)
    return _from(
        float(h.statistic),
        float(h.pvalue),
        n,
        alpha=alpha,
        extra={"group_sizes": sizes, "k_groups": len(groups)},
    )


# ---- Bonferroni correction --------------------------------------------------

def bonferroni_correct(pvalues: Sequence[float]) -> list[float]:
    """Bonferroni-correct a sequence of p-values (multiply by m, clip at 1.0)."""

    m = len(pvalues)
    return [min(1.0, p * m) for p in pvalues]


# ---- SAF threshold sensitivity (Phase H6) -----------------------------------

def saf_threshold_sensitivity(
    df: pd.DataFrame,
    *,
    deltas: Sequence[float] = (-0.05, 0.0, 0.05),
    base_threshold: float = 0.80,
    metric: str = "saf_overall",
    by: Sequence[str] = ("condition",),
) -> pd.DataFrame:
    """Return a DataFrame of binary pass rates at each threshold setting.

    For each δ in ``deltas`` and each (``by``) group in ``df``, compute
    the fraction of rows whose ``metric`` value is ≥ ``base_threshold +
    δ``. Returns a long-format DataFrame with columns matching ``by``
    plus ``delta``, ``threshold``, ``pass_rate``, ``n``.

    This function is what the :func:`clawsocialarena.analysis.figures.sensitivity_figure`
    plotter consumes, but exposing the tabular form separately lets the
    prereg reconciler cite the numbers directly.
    """

    rows: list[dict] = []
    if metric not in df.columns:
        return pd.DataFrame(columns=[*by, "delta", "threshold", "pass_rate", "n"])

    group_keys = list(by)
    grouped = df.groupby(group_keys, dropna=False) if group_keys else [(None, df)]
    for key, chunk in grouped:
        key_tuple = key if isinstance(key, tuple) else (key,)
        for delta in deltas:
            threshold = base_threshold + float(delta)
            n = int(chunk[metric].count())
            if n == 0:
                rate = float("nan")
            else:
                rate = float((chunk[metric] >= threshold).mean())
            row: dict = {
                "delta": float(delta),
                "threshold": threshold,
                "pass_rate": rate,
                "n": n,
            }
            for name, value in zip(group_keys, key_tuple):
                row[name] = value
            rows.append(row)
    return pd.DataFrame(rows)


# ---- Phase 6 back-compat ----------------------------------------------------

def paired_wilcoxon(
    df: pd.DataFrame,
    *,
    metric_family: str,
    metric_name: str,
    cond_a: str = "baseline",
    cond_b: str = "enforce",
) -> dict:
    """Legacy long-format paired Wilcoxon; returns a dict (Phase 6 shape)."""

    sub = df[
        (df["metric_family"] == metric_family) & (df["metric_name"] == metric_name)
    ]
    a = sub[sub["condition"] == cond_a].groupby("scenario_id")["value"].mean()
    b = sub[sub["condition"] == cond_b].groupby("scenario_id")["value"].mean()
    paired = pd.concat([a, b], axis=1, keys=[cond_a, cond_b]).dropna()
    if len(paired) < 2:
        return {"n": len(paired), "statistic": math.nan, "p_value": math.nan}
    diffs = paired[cond_b] - paired[cond_a]
    if (diffs == 0).all():
        return {"n": int(len(paired)), "statistic": 0.0, "p_value": 1.0}
    w = stats.wilcoxon(paired[cond_a], paired[cond_b])
    return {
        "n": int(len(paired)),
        "statistic": float(w.statistic),
        "p_value": float(w.pvalue),
    }


def kruskal_categories(
    df: pd.DataFrame,
    *,
    metric_family: str,
    metric_name: str,
    condition: str = "passive",
    category_col: str = "scenario_id",
) -> dict:
    """Legacy long-format Kruskal-Wallis; returns a dict (Phase 6 shape)."""

    sub = df[
        (df["metric_family"] == metric_family)
        & (df["metric_name"] == metric_name)
        & (df["condition"] == condition)
    ]
    groups = [g["value"].to_numpy() for _, g in sub.groupby(category_col) if len(g) > 0]
    if len(groups) < 2:
        return {"k": len(groups), "statistic": math.nan, "p_value": math.nan}
    h = stats.kruskal(*groups)
    return {
        "k": len(groups),
        "statistic": float(h.statistic),
        "p_value": float(h.pvalue),
    }


def bonferroni(p_values: list[float]) -> list[float]:
    """Bonferroni-correct a list of p-values; preserved for Phase 6 callers."""

    return bonferroni_correct(p_values)
