"""Statistical tests — Wilcoxon signed-rank (paired), Kruskal-Wallis (multi-group).

Used for condition comparisons across scenarios. Bonferroni correction is
applied when testing multiple hypothesis families simultaneously.
"""

from __future__ import annotations

import math

import pandas as pd
from scipy import stats


def paired_wilcoxon(
    df: pd.DataFrame,
    *,
    metric_family: str,
    metric_name: str,
    cond_a: str = "baseline",
    cond_b: str = "enforce",
) -> dict:
    """Paired Wilcoxon signed-rank between ``cond_a`` and ``cond_b`` on shared scenarios."""
    sub = df[
        (df["metric_family"] == metric_family) & (df["metric_name"] == metric_name)
    ]
    a = sub[sub["condition"] == cond_a].groupby("scenario_id")["value"].mean()
    b = sub[sub["condition"] == cond_b].groupby("scenario_id")["value"].mean()
    paired = pd.concat([a, b], axis=1, keys=[cond_a, cond_b]).dropna()
    if len(paired) < 2:
        return {"n": len(paired), "statistic": math.nan, "p_value": math.nan}

    # If differences are all zero, scipy raises — short-circuit to p=1.
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
    """Kruskal-Wallis H-test across categories.

    Groups the filtered (metric_family, metric_name, condition) slice by
    ``category_col`` and runs a non-parametric ANOVA equivalent. Real usage
    would typically group by scenario-spec category (CD/MC/CU/...); wire that
    in once aggregation includes it.
    """
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
    """Bonferroni-correct a list of p-values (multiply by m, clip at 1.0)."""
    m = len(p_values)
    return [min(1.0, p * m) for p in p_values]
