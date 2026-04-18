"""Aggregator contract (Phase 6 long-format path).

Phase H introduces a wider, one-row-per-scorecard CSV as the default
:func:`clawsocialarena.analysis.aggregator.aggregate_to_csv` output.
The legacy long-format path stays reachable via ``wide=False`` and is
exercised here so the Phase 6 callers that grouped by ``metric_family``
/ ``metric_name`` keep working.
"""

from pathlib import Path

from clawsocialarena.analysis.aggregator import aggregate_to_csv


def test_aggregate_produces_nonempty_csv(tmp_path: Path, synthetic_results_root: Path):
    out = tmp_path / "long.csv"
    n = aggregate_to_csv(synthetic_results_root, out, wide=False)
    assert n > 0
    content = out.read_text()
    header = content.splitlines()[0]
    assert "scenario_id" in header
    assert "condition" in header
    assert "model" in header
    # At least one SAF overall row should be present.
    assert "saf,overall" in content


def test_aggregate_includes_all_metric_families(
    tmp_path: Path, synthetic_results_root: Path
):
    out = tmp_path / "long.csv"
    aggregate_to_csv(synthetic_results_root, out, wide=False)
    content = out.read_text()
    for family in ("saf", "task", "privacy", "security"):
        assert f",{family}," in content


def test_aggregate_carries_meta_fields(tmp_path: Path, synthetic_results_root: Path):
    out = tmp_path / "long.csv"
    aggregate_to_csv(synthetic_results_root, out, wide=False)
    content = out.read_text()
    # Each condition ("baseline", "passive", "enforce") should surface
    # somewhere in the column for condition.
    for cond in ("baseline", "passive", "enforce"):
        assert cond in content
    for model in ("claude", "gpt"):
        assert model in content
