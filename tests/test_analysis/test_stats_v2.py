"""Statistical tests v2 — Phase H wide-format signatures."""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from clawsocialarena.analysis.aggregator import aggregate_to_csv
from clawsocialarena.analysis.stats import (
    StatTestResult,
    bonferroni_correct,
    kruskal_wallis,
    saf_threshold_sensitivity,
    wilcoxon_paired,
)
from clawsocialarena.analysis.tables import load_long_csv

from tests.test_analysis.fixtures import build_synthetic_scorecards


def _prep(tmp_path: Path) -> pd.DataFrame:
    root = build_synthetic_scorecards(tmp_path)
    out = tmp_path / "long.csv"
    aggregate_to_csv(root, out)
    return load_long_csv(out)


def test_wilcoxon_paired_detects_condition_shift(tmp_path: Path):
    df = _prep(tmp_path)
    # ASR: baseline 0.40, enforce 0.03. Applies across every category so
    # all 8 paired (model × scenario) diffs are nonzero and same-sign.
    result = wilcoxon_paired(
        df,
        metric="asr",
        conditions=("baseline", "enforce"),
    )
    assert isinstance(result, StatTestResult)
    assert result.n > 0
    assert result.significant is True
    assert result.pvalue < 0.05


def test_wilcoxon_paired_reports_no_shift_when_tsr_constant_under_baseline_passive(tmp_path: Path):
    df = _prep(tmp_path)
    # TSR is identical between baseline and passive (both 1.0); paired diffs
    # are all zero -> p=1.0 exactly.
    result = wilcoxon_paired(
        df,
        metric="tsr",
        conditions=("baseline", "passive"),
    )
    assert result.pvalue == 1.0
    assert result.statistic == 0.0
    assert result.significant is False


def test_wilcoxon_paired_returns_nan_when_insufficient_data():
    df = pd.DataFrame(
        {
            "scenario_id": ["s1"],
            "model": ["m1"],
            "condition": ["baseline"],
            "tsr": [1.0],
        }
    )
    result = wilcoxon_paired(df, metric="tsr", conditions=("baseline", "enforce"))
    assert math.isnan(result.pvalue)
    assert result.significant is False


def test_kruskal_wallis_across_categories(tmp_path: Path):
    df = _prep(tmp_path)
    # Passive condition + SAF overall across categories; fixture stamps equal
    # values so the test runs without raising but may have NaN p on exact ties.
    result = kruskal_wallis(
        df,
        metric="saf_overall",
        group_col="category",
        condition="passive",
    )
    assert isinstance(result, StatTestResult)
    assert result.n > 0
    assert "group_sizes" in result.extra


def test_kruskal_wallis_detects_difference_between_conditions(tmp_path: Path):
    df = _prep(tmp_path)
    # Drop ``passive`` so ASR differs across the two remaining groups.
    result = kruskal_wallis(
        df[df["condition"].isin(["baseline", "enforce"])],
        metric="asr",
        group_col="condition",
    )
    assert result.n > 0
    assert result.significant is True
    assert result.pvalue < 0.05


def test_bonferroni_correct_matches_raw_when_single_test():
    raw = [0.01]
    adj = bonferroni_correct(raw)
    assert adj == [0.01]


def test_bonferroni_correct_scales_by_family_size():
    raw = [0.01, 0.04, 0.3]
    adj = bonferroni_correct(raw)
    assert adj[0] == pytest.approx(0.03)
    assert adj[1] == pytest.approx(0.12)
    assert adj[2] == pytest.approx(0.9)


def test_bonferroni_correct_clips_at_one():
    assert bonferroni_correct([0.5, 0.6]) == [1.0, 1.0]


def test_saf_threshold_sensitivity_returns_full_grid(tmp_path: Path):
    df = _prep(tmp_path)
    table = saf_threshold_sensitivity(
        df,
        deltas=(-0.05, 0.0, 0.05),
        by=("condition",),
    )
    # 3 conditions × 3 deltas = 9 rows.
    assert len(table) == 9
    for col in ("condition", "delta", "threshold", "pass_rate", "n"):
        assert col in table.columns
    # All rates bounded in [0, 1].
    assert (table["pass_rate"] >= 0.0).all()
    assert (table["pass_rate"] <= 1.0).all()


def test_saf_threshold_sensitivity_threshold_shift_lowers_pass_rate_monotonically(tmp_path: Path):
    df = _prep(tmp_path)
    table = saf_threshold_sensitivity(
        df,
        deltas=(-0.1, -0.05, 0.0, 0.05, 0.1),
        by=("condition",),
    )
    # Pass rate must be non-increasing in threshold for any single condition.
    for cond, chunk in table.groupby("condition"):
        rates = chunk.sort_values("delta")["pass_rate"].tolist()
        for lower, higher in zip(rates, rates[1:]):
            assert higher <= lower + 1e-9, f"rate rose with threshold for {cond}"
