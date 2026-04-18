"""H6 sensitivity analysis — SAF threshold sweep + figure."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from clawsocialarena.analysis.aggregator import aggregate_to_csv
from clawsocialarena.analysis.figures import sensitivity_figure
from clawsocialarena.analysis.stats import saf_threshold_sensitivity
from clawsocialarena.analysis.tables import load_long_csv

from tests.test_analysis.fixtures import build_synthetic_scorecards


def _prep(tmp_path: Path) -> pd.DataFrame:
    root = build_synthetic_scorecards(tmp_path)
    out = tmp_path / "long.csv"
    aggregate_to_csv(root, out)
    return load_long_csv(out)


def test_saf_sensitivity_zero_delta_matches_base_threshold(tmp_path: Path):
    df = _prep(tmp_path)
    table = saf_threshold_sensitivity(
        df, deltas=(0.0,), base_threshold=0.80, by=("condition",)
    )
    # 3 conditions in the fixture at delta=0 -> 3 rows.
    assert len(table) == 3
    # At threshold 0.80, every condition's SAF overall (0.80, 0.90, 0.92) passes.
    assert (table["pass_rate"] == 1.0).all()


def test_saf_sensitivity_positive_delta_culls_baseline_first(tmp_path: Path):
    df = _prep(tmp_path)
    # +0.05 shifts threshold to 0.85 -> baseline (0.80) fails, passive + enforce pass.
    table = saf_threshold_sensitivity(
        df, deltas=(0.05,), base_threshold=0.80, by=("condition",)
    )
    rates = dict(zip(table["condition"], table["pass_rate"]))
    assert rates["baseline"] == 0.0
    assert rates["passive"] == 1.0
    assert rates["enforce"] == 1.0


def test_sensitivity_figure_delegates_to_stats(tmp_path: Path):
    df = _prep(tmp_path)
    fig = sensitivity_figure(df, threshold_deltas=(-0.05, 0.0, 0.05))
    ax = fig.axes[0]
    # 3 conditions -> 3 lines.
    lines_by_label = {line.get_label(): line for line in ax.lines}
    assert set(lines_by_label) == {"baseline", "passive", "enforce"}
    # Zero-delta point is the middle x for every line, with y=1.0 across all
    # conditions on the fixture.
    for line in ax.lines:
        xs = list(line.get_xdata())
        ys = list(line.get_ydata())
        assert 0.0 in xs
        assert ys[xs.index(0.0)] == 1.0


def test_sensitivity_sweep_is_nonincreasing(tmp_path: Path):
    df = _prep(tmp_path)
    table = saf_threshold_sensitivity(
        df,
        deltas=(-0.1, -0.05, 0.0, 0.05, 0.1),
        by=("condition", "category"),
    )
    # Scoped by (condition × category) the pass rate is non-increasing in δ.
    for (_cond, _cat), chunk in table.groupby(["condition", "category"]):
        rates = chunk.sort_values("delta")["pass_rate"].tolist()
        for lower, higher in zip(rates, rates[1:]):
            assert higher <= lower + 1e-9
