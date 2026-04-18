"""Tables — legacy long-format signatures (Phase 6 compat)."""

from clawsocialarena.analysis.aggregator import aggregate_to_csv
from clawsocialarena.analysis.tables import (
    headline_table_long,
    load_long_csv,
    model_comparison_table_long,
    rewrite_quality_table_long,
    to_latex,
    to_markdown,
)


def _prep(tmp_path, synthetic_results_root):
    out = tmp_path / "long.csv"
    aggregate_to_csv(synthetic_results_root, out, wide=False)
    return load_long_csv(out)


def test_headline_table_has_ci(tmp_path, synthetic_results_root):
    df = _prep(tmp_path, synthetic_results_root)
    table = headline_table_long(df)
    assert {"mean", "ci_low", "ci_high", "n"} <= set(table.columns)
    assert (table["n"] > 0).all()
    # CI should respect mean.
    assert (table["ci_low"] <= table["mean"]).all()
    assert (table["mean"] <= table["ci_high"]).all()


def test_model_comparison_table(tmp_path, synthetic_results_root):
    df = _prep(tmp_path, synthetic_results_root)
    table = model_comparison_table_long(df, condition="passive")
    # One row per model (claude, gpt).
    assert len(table) >= 2
    assert "model" in table.columns
    # SAF overall column should exist after pivoting.
    assert "overall" in table.columns


def test_rewrite_quality_table_has_delta(tmp_path, synthetic_results_root):
    df = _prep(tmp_path, synthetic_results_root)
    table = rewrite_quality_table_long(df)
    assert "delta_enforce_minus_passive" in table.columns
    # All scenarios have TSR=1.0 in fixtures, so delta should be 0.
    assert (table["delta_enforce_minus_passive"].abs() < 1e-9).all()


def test_render_markdown_and_latex(tmp_path, synthetic_results_root):
    df = _prep(tmp_path, synthetic_results_root)
    table = headline_table_long(df)
    md = to_markdown(table)
    tex = to_latex(table)
    assert "|" in md  # markdown row delimiter
    assert "tabular" in tex
