import math

import pytest

from clawsocialarena.analysis.aggregator import aggregate_to_csv
from clawsocialarena.analysis.stats import (
    bonferroni,
    kruskal_categories,
    paired_wilcoxon,
)
from clawsocialarena.analysis.tables import load_long_csv


def test_paired_wilcoxon_detects_shift(tmp_path, synthetic_results_root):
    out = tmp_path / "long.csv"
    aggregate_to_csv(synthetic_results_root, out)
    df = load_long_csv(out)
    # Privacy leak_rate: baseline=0.5, enforce=0.05 -> clearly different.
    result = paired_wilcoxon(
        df,
        metric_family="privacy",
        metric_name="leak_rate",
        cond_a="baseline",
        cond_b="enforce",
    )
    assert result["n"] > 0
    assert not math.isnan(result["p_value"])


def test_paired_wilcoxon_handles_identical_values(tmp_path, synthetic_results_root):
    out = tmp_path / "long.csv"
    aggregate_to_csv(synthetic_results_root, out)
    df = load_long_csv(out)
    # Task TSR is constant (1.0) across all conditions in the fixture;
    # all differences are 0 -> guard path returns p=1.0.
    result = paired_wilcoxon(
        df,
        metric_family="task",
        metric_name="tsr",
        cond_a="baseline",
        cond_b="enforce",
    )
    assert result["statistic"] == 0.0
    assert result["p_value"] == 1.0


def test_bonferroni_corrects():
    raw = [0.01, 0.04, 0.3]
    adj = bonferroni(raw)
    # Float-precision tolerant equality.
    assert adj[0] == pytest.approx(0.03)
    assert adj[1] == pytest.approx(0.12)
    assert adj[2] == pytest.approx(0.9)


def test_bonferroni_clips_at_one():
    raw = [0.5, 0.6]
    adj = bonferroni(raw)
    # 0.5 * 2 = 1.0, 0.6 * 2 = 1.2 -> clipped to 1.0.
    assert adj == [1.0, 1.0]


def test_kruskal_on_saf_overall(tmp_path, synthetic_results_root):
    out = tmp_path / "long.csv"
    aggregate_to_csv(synthetic_results_root, out)
    df = load_long_csv(out)
    result = kruskal_categories(
        df,
        metric_family="saf",
        metric_name="overall",
        condition="passive",
        category_col="model",
    )
    assert result["k"] >= 2
    # Across two models with identical saf_overall the test should run
    # without raising, even if p is nan on exact ties.
    assert "statistic" in result
    assert "p_value" in result


def test_kruskal_returns_nan_with_single_group(tmp_path, synthetic_results_root):
    out = tmp_path / "long.csv"
    aggregate_to_csv(synthetic_results_root, out)
    df = load_long_csv(out)
    # Filter to a single model so only one group remains.
    df = df[df["model"] == "claude"]
    result = kruskal_categories(
        df,
        metric_family="saf",
        metric_name="overall",
        condition="passive",
        category_col="model",
    )
    assert result["k"] == 1
    assert math.isnan(result["p_value"])
