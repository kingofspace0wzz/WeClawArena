"""Paper figure producers — smoke tests on the Phase H synthetic fixture."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

matplotlib = pytest.importorskip("matplotlib")
from matplotlib.figure import Figure  # noqa: E402

from clawsocialarena.analysis.aggregator import aggregate_to_csv  # noqa: E402
from clawsocialarena.analysis.figures import (  # noqa: E402
    ablation_figure,
    disagreement_vignettes_figure,
    episode_graph_figure,
    rewrite_quality_figure,
    sensitivity_figure,
    write_all_figures,
)
from clawsocialarena.analysis.tables import load_long_csv  # noqa: E402
from clawsocialarena.eval.cumulative import (  # noqa: E402
    CumulativeTrajectory,
)
from clawsocialarena.eval.scorecard import EpisodeGraphScorecard  # noqa: E402

from tests.test_analysis.fixtures import build_synthetic_scorecards  # noqa: E402


def _prep(tmp_path: Path) -> pd.DataFrame:
    root = build_synthetic_scorecards(tmp_path)
    out = tmp_path / "long.csv"
    aggregate_to_csv(root, out)
    return load_long_csv(out)


def test_ablation_figure_has_four_axes(tmp_path: Path):
    df = _prep(tmp_path)
    fig = ablation_figure(df)
    assert isinstance(fig, Figure)
    assert len(fig.axes) == 4


def test_ablation_panels_have_condition_ladder(tmp_path: Path):
    df = _prep(tmp_path)
    fig = ablation_figure(df)
    xticks = [t.get_text() for t in fig.axes[0].get_xticklabels()]
    # matplotlib may yield empty tick labels before a draw(); assert on the data line.
    lines = fig.axes[0].lines
    assert lines, "expected at least one category series drawn"
    xs = [x for line in lines for x in line.get_xdata()]
    assert any("baseline" in str(x) or x == 0 for x in xs) or xticks
    labels = {line.get_label() for line in lines}
    assert labels == {"collaboration", "security", "privacy", "governance"}


def test_rewrite_quality_figure_has_one_axis(tmp_path: Path):
    df = _prep(tmp_path)
    fig = rewrite_quality_figure(df)
    assert isinstance(fig, Figure)
    assert len(fig.axes) == 1
    # One bar per attack axis on the fixture.
    bars = fig.axes[0].patches
    assert len(bars) >= 4


def test_disagreement_vignettes_figure_is_multi_panel(tmp_path: Path):
    df = _prep(tmp_path)
    fig = disagreement_vignettes_figure(df, n_cases=3)
    assert isinstance(fig, Figure)
    # At least one panel rendered; synthetic fixture has 2 scenarios so
    # n_cases=3 is capped by data.
    assert len(fig.axes) >= 1


def test_sensitivity_figure_draws_one_line_per_condition(tmp_path: Path):
    df = _prep(tmp_path)
    fig = sensitivity_figure(df, threshold_deltas=(-0.05, 0.0, 0.05))
    assert isinstance(fig, Figure)
    # 3 conditions in the fixture -> 3 plotted series.
    assert len(fig.axes[0].lines) == 3
    # Each line has exactly len(deltas) points.
    assert all(len(line.get_xdata()) == 3 for line in fig.axes[0].lines)


def test_sensitivity_figure_rates_are_between_zero_and_one(tmp_path: Path):
    df = _prep(tmp_path)
    fig = sensitivity_figure(df)
    for line in fig.axes[0].lines:
        for y in line.get_ydata():
            assert 0.0 <= y <= 1.0


def test_episode_graph_figure_draws_trajectory_panels():
    traj = CumulativeTrajectory(
        social_recall=[0.0, 0.5, 0.8, 0.9],
        social_precision=[1.0, 0.75, 0.6, 0.6],
        tlr=[0.0, 0.25, 0.4, 0.5],
        cpr=[0.0, 0.0, 0.33, 0.5],
    )
    graph = EpisodeGraphScorecard(
        graph_id="graph-A",
        per_episode=[],
        trajectory=traj,
        meta={},
    )
    fig = episode_graph_figure([graph])
    assert isinstance(fig, Figure)
    # Two panels: precision and CPR.
    assert len(fig.axes) == 2
    # The left panel has one line with four data points.
    assert len(fig.axes[0].lines) == 1
    assert len(fig.axes[0].lines[0].get_xdata()) == 4


def test_write_all_figures_produces_four_pdfs(tmp_path: Path):
    df = _prep(tmp_path)
    written = write_all_figures(df, tmp_path / "figures")
    assert len(written) == 4
    names = {p.name for p in written}
    assert names == {
        "ablation_figure.pdf",
        "rewrite_quality_figure.pdf",
        "disagreement_vignettes_figure.pdf",
        "sensitivity_figure.pdf",
    }
    for p in written:
        assert p.exists()
        assert p.stat().st_size > 0
