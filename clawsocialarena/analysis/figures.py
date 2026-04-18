"""Paper figures — matplotlib producers for the four Phase H figures.

Every function takes the wide Phase H DataFrame (or an equivalent input)
and returns a :class:`matplotlib.figure.Figure`. The CLI wrapper
``python -m clawsocialarena.analysis figures --csv <path> --out <dir>/``
writes all four as PDFs alongside the episode-graph appendix figure.

Producers:

- :func:`ablation_figure` — ΔTSR / ΔPrivacy / ΔSecurity baseline -> passive
  -> enforce, broken by attack axis (category).
- :func:`rewrite_quality_figure` — TSR(enforce) − TSR(passive) per category.
- :func:`disagreement_vignettes_figure` — three-panel case studies
  comparing SAF vs vanilla-AA per scenario.
- :func:`sensitivity_figure` — binary SAF pass-rate at each threshold
  shift (spec §5.7 sensitivity sweep).
- :func:`episode_graph_figure` — cumulative Social Precision(t) + CPR(t)
  trajectories per graph (episode-graph stratum appendix).

The module uses matplotlib's ``Agg`` backend so it works on headless CI
without a DISPLAY variable.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib
matplotlib.use("Agg", force=False)

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from matplotlib.figure import Figure  # noqa: E402


if TYPE_CHECKING:
    from clawsocialarena.eval.scorecard import EpisodeGraphScorecard


_CONDITION_ORDER: tuple[str, ...] = ("baseline", "passive", "enforce")
_PRIVACY_METRICS: tuple[str, ...] = ("cdlr", "culr", "mplr", "halr", "cslr")


def _group_mean(df: pd.DataFrame, *, by: Sequence[str], metric: str) -> pd.DataFrame:
    """Group-by mean of a single metric column; returns a tidy DataFrame."""

    return (
        df.groupby(list(by), dropna=False)[metric]
        .mean()
        .reset_index()
        .rename(columns={metric: "mean"})
    )


def ablation_figure(df: pd.DataFrame) -> Figure:
    """Three-panel figure: ΔTSR / ΔPrivacy / ΔSecurity across conditions × category.

    Each panel plots mean ± SD across scenarios, with one line per
    category (``family`` could also be used; category is the attack
    axis). X axis is the condition ladder.
    """

    df = df.copy()
    # Mean across any scalar privacy leak columns present -> one "privacy" series.
    present_priv = [c for c in _PRIVACY_METRICS if c in df.columns]
    if present_priv:
        df["privacy_mean"] = df[present_priv].mean(axis=1)
    else:
        df["privacy_mean"] = 0.0

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    metrics = (
        ("tsr", "TSR (↑)"),
        ("privacy_mean", "Privacy leak (↓)"),
        ("asr", "Security ASR (↓)"),
    )
    categories = sorted(df["category"].dropna().unique())
    for ax, (col, label) in zip(axes, metrics):
        for cat in categories:
            sub = df[df["category"] == cat]
            means = [
                float(sub[sub["condition"] == c][col].mean())
                for c in _CONDITION_ORDER
            ]
            ax.plot(_CONDITION_ORDER, means, marker="o", label=str(cat))
        ax.set_title(label)
        ax.set_xlabel("Condition")
        ax.grid(True, alpha=0.3)
    axes[0].set_ylabel("Mean metric value")
    if categories:
        axes[-1].legend(title="Category", loc="best")
    fig.tight_layout()
    return fig


def rewrite_quality_figure(df: pd.DataFrame) -> Figure:
    """Bar plot of TSR(enforce) − TSR(passive) per category."""

    sub = df[df["condition"].isin(["passive", "enforce"])].copy()
    pivot = sub.pivot_table(
        index=["category", "model", "scenario_id"],
        columns="condition",
        values="tsr",
        aggfunc="mean",
    )
    if {"passive", "enforce"} <= set(pivot.columns):
        pivot["delta"] = pivot["enforce"] - pivot["passive"]
        per_cat = (
            pivot.reset_index()
            .groupby("category")["delta"]
            .agg(["mean", "std", "count"])
            .reset_index()
        )
    else:
        per_cat = pd.DataFrame(columns=["category", "mean", "std", "count"])

    fig, ax = plt.subplots(figsize=(8, 4))
    if not per_cat.empty:
        xs = np.arange(len(per_cat))
        yerr = per_cat["std"].fillna(0.0).to_numpy()
        ax.bar(xs, per_cat["mean"], yerr=yerr, capsize=6)
        ax.set_xticks(xs)
        ax.set_xticklabels(per_cat["category"])
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.set_ylabel("TSR(enforce) − TSR(passive)")
    ax.set_xlabel("Category")
    ax.set_title("Rewrite-quality delta per category")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    return fig


def disagreement_vignettes_figure(df: pd.DataFrame, *, n_cases: int = 3) -> Figure:
    """Three-panel figure contrasting SAF overall vs vanilla-AA on a few scenarios.

    Picks ``n_cases`` scenarios with the largest gap between ``saf_overall``
    and a ``vaa_overall`` column (if present). Falls back to arbitrary
    scenario ids when the vanilla-AA column is missing so the figure
    still renders on Phase H synthetic fixtures.
    """

    passive = df[df["condition"] == "passive"].copy()
    if passive.empty:
        passive = df.copy()

    # If a vanilla-AA column is present, rank by absolute gap. Else just pick the
    # first n_cases scenario ids deterministically so the figure is reproducible.
    vaa_col = None
    for candidate in ("vaa_overall", "vanilla_aa_overall"):
        if candidate in passive.columns:
            vaa_col = candidate
            break

    if vaa_col is not None:
        passive["gap"] = (passive[vaa_col] - passive["saf_overall"]).abs()
        scenarios = (
            passive.sort_values("gap", ascending=False)["scenario_id"]
            .drop_duplicates()
            .head(n_cases)
            .tolist()
        )
    else:
        scenarios = sorted(passive["scenario_id"].unique())[:n_cases]

    fig, axes = plt.subplots(1, max(1, len(scenarios)), figsize=(4 * max(1, len(scenarios)), 4))
    if len(scenarios) <= 1:
        axes = [axes]
    for ax, sid in zip(axes, scenarios):
        sub = passive[passive["scenario_id"] == sid]
        saf_score = float(sub["saf_overall"].mean() if not sub.empty else 0.0)
        vaa_score = (
            float(sub[vaa_col].mean())
            if vaa_col is not None and not sub.empty
            else float("nan")
        )
        bars = [saf_score, vaa_score if not np.isnan(vaa_score) else 0.0]
        ax.bar(["SAF", "Vanilla-AA"], bars, color=["#3b7bbe", "#d97444"])
        ax.set_ylim(0.0, 1.05)
        ax.set_title(f"{sid}")
        ax.set_ylabel("Auditability score")
        ax.grid(True, axis="y", alpha=0.3)
    fig.suptitle("SAF vs vanilla-AA disagreement vignettes")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig


def sensitivity_figure(
    df: pd.DataFrame,
    *,
    threshold_deltas: Sequence[float] = (-0.05, 0.0, 0.05),
    threshold_base: float = 0.80,
) -> Figure:
    """Binary SAF pass rate swept across ``threshold_base ± δ``, per condition.

    Delegates the binary-pass-rate computation to
    :func:`clawsocialarena.analysis.stats.saf_threshold_sensitivity` so
    the figure and the H6 statistics agree on every number.
    """

    # Import locally to avoid a stats -> figures circular dependency risk.
    from clawsocialarena.analysis.stats import saf_threshold_sensitivity

    table = saf_threshold_sensitivity(
        df,
        deltas=threshold_deltas,
        base_threshold=threshold_base,
        by=("condition",),
    )

    fig, ax = plt.subplots(figsize=(8, 4))
    conditions = [c for c in _CONDITION_ORDER if c in set(table["condition"].dropna())]
    deltas = list(threshold_deltas)
    for cond in conditions:
        sub = table[table["condition"] == cond].sort_values("delta")
        ax.plot(sub["delta"], sub["pass_rate"], marker="o", label=cond)
    ax.set_xlabel("Threshold shift δ (applied to SAF pass bar)")
    ax.set_ylabel("Binary SAF pass rate")
    ax.set_title("SAF threshold sensitivity sweep")
    if conditions:
        ax.legend(title="Condition")
    ax.grid(True, alpha=0.3)
    # Keep the y-range deterministic so tests can assert on it.
    ax.set_ylim(-0.02, 1.05)
    _ = deltas  # deltas passed via ``table`` — retained for signature parity.
    fig.tight_layout()
    return fig


def episode_graph_figure(
    episode_graph_scorecards: Iterable["EpisodeGraphScorecard"],
) -> Figure:
    """Cumulative Social Precision(t) + CPR(t) trajectories per episode graph.

    Expects an iterable of :class:`EpisodeGraphScorecard` objects whose
    ``trajectory`` attribute is populated. Draws two panels side by side
    (precision and CPR), one line per graph.
    """

    graphs = list(episode_graph_scorecards)
    fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(12, 4))
    for eg in graphs:
        if eg.trajectory is None:
            continue
        ts = list(range(1, len(eg.trajectory.social_precision) + 1))
        ax_left.plot(ts, eg.trajectory.social_precision, marker="o", label=eg.graph_id)
        ax_right.plot(ts, eg.trajectory.cpr, marker="s", label=eg.graph_id)
    ax_left.set_title("Social Precision(t)")
    ax_left.set_xlabel("Episode index")
    ax_left.set_ylabel("Precision")
    ax_left.set_ylim(0.0, 1.05)
    ax_left.grid(True, alpha=0.3)
    ax_right.set_title("Cumulative Propagation Rate CPR(t)")
    ax_right.set_xlabel("Episode index")
    ax_right.set_ylabel("CPR")
    ax_right.set_ylim(0.0, 1.05)
    ax_right.grid(True, alpha=0.3)
    if graphs:
        ax_left.legend(title="Graph", loc="lower right")
    fig.tight_layout()
    return fig


# ---- CLI helper --------------------------------------------------------------

def write_all_figures(df: pd.DataFrame, out_dir: Path) -> list[Path]:
    """Render all four main figures as PDFs under ``out_dir``.

    Returns the list of paths written, in a stable order. The
    episode-graph figure is only written when the caller passes a
    non-empty ``episode_graphs`` list; this top-level helper only
    handles the four per-scorecard figures.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[tuple[Path, Figure]] = [
        (out_dir / "ablation_figure.pdf", ablation_figure(df)),
        (out_dir / "rewrite_quality_figure.pdf", rewrite_quality_figure(df)),
        (out_dir / "disagreement_vignettes_figure.pdf", disagreement_vignettes_figure(df)),
        (out_dir / "sensitivity_figure.pdf", sensitivity_figure(df)),
    ]
    written: list[Path] = []
    for path, fig in outputs:
        fig.savefig(path)
        plt.close(fig)
        written.append(path)
    return written
