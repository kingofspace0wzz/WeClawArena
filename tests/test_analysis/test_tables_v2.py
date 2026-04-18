"""Tables v2 — wide-format Phase H tables."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from clawsocialarena.analysis.aggregator import aggregate_to_csv
from clawsocialarena.analysis.tables import (
    headline_table,
    headline_table_df,
    load_long_csv,
    model_comparison_table,
    model_comparison_table_df,
    rewrite_quality_table,
    rewrite_quality_table_df,
)

from tests.test_analysis.fixtures import build_synthetic_scorecards


def _prep(tmp_path: Path) -> pd.DataFrame:
    root = build_synthetic_scorecards(tmp_path)
    out = tmp_path / "long.csv"
    aggregate_to_csv(root, out)
    return load_long_csv(out)


def test_headline_table_returns_md_and_latex(tmp_path: Path):
    df = _prep(tmp_path)
    md, tex = headline_table(df)
    assert isinstance(md, str)
    assert isinstance(tex, str)
    assert "|" in md  # markdown row separator
    assert "tabular" in tex  # latex environment


def test_headline_table_df_has_expected_columns(tmp_path: Path):
    df = _prep(tmp_path)
    table = headline_table_df(df)
    for col in (
        "condition",
        "category",
        "live_or_replay",
        "metric",
        "mean",
        "ci_low",
        "ci_high",
        "n",
    ):
        assert col in table.columns
    # Condition effect: SAF overall should be highest under enforce, lowest under baseline.
    saf = table[table["metric"] == "saf_overall"]
    saf_by_cond = saf.groupby("condition")["mean"].mean()
    assert saf_by_cond["enforce"] >= saf_by_cond["baseline"]


def test_model_comparison_held_at_passive(tmp_path: Path):
    df = _prep(tmp_path)
    md, tex = model_comparison_table(df, condition="passive")
    assert "|" in md
    assert "tabular" in tex
    frame = model_comparison_table_df(df, condition="passive")
    # 4 models × 2 categories (times live_or_replay count).
    assert set(frame["model"]) == {
        "claude-sonnet-4-6",
        "gpt-5-mini",
        "gemini-2-5-flash",
        "llama-4-maverick",
    }
    assert "saf_overall" in frame.columns
    assert "psi" in frame.columns


def test_rewrite_quality_shows_enforce_minus_passive(tmp_path: Path):
    df = _prep(tmp_path)
    md, tex = rewrite_quality_table(df)
    assert "|" in md
    assert "tabular" in tex
    frame = rewrite_quality_table_df(df)
    assert "delta_mean" in frame.columns
    # Fixture sets TSR_enforce=0.95, TSR_passive=1.0 -> delta = -0.05.
    # Averaged over (category, live_or_replay), rounded for tolerance.
    for delta in frame["delta_mean"]:
        assert abs(delta - (-0.05)) < 1e-6


def test_tables_include_live_or_replay_column(tmp_path: Path):
    df = _prep(tmp_path)
    for frame in (
        headline_table_df(df),
        model_comparison_table_df(df),
        rewrite_quality_table_df(df),
    ):
        assert "live_or_replay" in frame.columns


def test_headline_empty_when_no_matching_metric(tmp_path: Path):
    # Build a frame missing every headline metric.
    df = pd.DataFrame(
        {
            "scenario_id": ["x"],
            "category": ["CD"],
            "family": ["auditability"],
            "model": ["claude"],
            "condition": ["passive"],
            "live_or_replay": ["live"],
        }
    )
    out = headline_table_df(df)
    # Empty because none of the metric columns exist.
    assert out.empty
