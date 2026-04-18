from clawsocialarena.analysis.aggregator import aggregate_to_csv
from clawsocialarena.analysis.prereg_check import reconcile, render_report


def test_reconcile_returns_h2_h4(tmp_path, synthetic_results_root):
    out = tmp_path / "long.csv"
    aggregate_to_csv(synthetic_results_root, out, wide=False)
    results = reconcile(out)
    hyps = {r["hypothesis"] for r in results}
    assert "H2" in hyps
    assert "H4" in hyps


def test_render_report_produces_markdown(tmp_path, synthetic_results_root):
    out = tmp_path / "long.csv"
    aggregate_to_csv(synthetic_results_root, out, wide=False)
    report = render_report(reconcile(out))
    assert "# Pre-registration reconciliation" in report
    assert "## H2" in report
    assert "## H4" in report
    # Every hypothesis block should label its verdict.
    assert "Verdict:" in report


def test_h4_verdict_reports_fraction(tmp_path, synthetic_results_root):
    out = tmp_path / "long.csv"
    aggregate_to_csv(synthetic_results_root, out, wide=False)
    results = reconcile(out)
    h4 = next(r for r in results if r["hypothesis"] == "H4")
    # Fixture stamps vanilla_aa_overall (0.95) > saf overall (0.9) on all
    # 4 passive scenarios -> fraction=1.0 and verdict=supported.
    assert h4["n"] > 0
    assert h4["frac_vaa_over_saf"] == 1.0
    assert h4["verdict"] == "supported"
