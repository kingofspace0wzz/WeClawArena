"""Pre-registration reconciliation v2 — Phase H wide-format verdicts."""

from __future__ import annotations

from pathlib import Path

from clawsocialarena.analysis.aggregator import aggregate_to_csv
from clawsocialarena.analysis.prereg_check import (
    HypothesisResult,
    evaluate_hypotheses,
    reconcile_wide,
    render_markdown_report,
    write_report,
)
from clawsocialarena.analysis.tables import load_long_csv

from tests.test_analysis.fixtures import build_synthetic_scorecards


def _prep(tmp_path: Path):
    root = build_synthetic_scorecards(tmp_path)
    csv = tmp_path / "long.csv"
    aggregate_to_csv(root, csv)
    return csv, load_long_csv(csv)


def test_evaluate_hypotheses_covers_h1_through_h5(tmp_path: Path):
    _, df = _prep(tmp_path)
    results = evaluate_hypotheses(df)
    assert [r.hypothesis for r in results] == ["H1", "H2", "H3", "H4", "H5"]
    for r in results:
        assert isinstance(r, HypothesisResult)


def test_h1_passes_on_fixture(tmp_path: Path):
    _, df = _prep(tmp_path)
    [h1] = [r for r in evaluate_hypotheses(df) if r.hypothesis == "H1"]
    # Fixture stamps attribution (τ), phase_scoped_policy (φ), and
    # identity_governance (γ) as the three weakest dims under passive.
    assert h1.verdict == "supported", h1.summary
    assert "identity_governance" in h1.statistics


def test_h2_passes_on_fixture(tmp_path: Path):
    _, df = _prep(tmp_path)
    [h2] = [r for r in evaluate_hypotheses(df) if r.hypothesis == "H2"]
    assert h2.verdict == "supported", h2.summary
    assert h2.statistics["privacy_pvalue"] < 0.05
    assert h2.statistics["security_pvalue"] < 0.05
    assert h2.statistics["governance_pvalue"] < 0.05
    assert h2.statistics["governance_enforce_mean"] < h2.statistics[
        "governance_baseline_mean"
    ]
    assert h2.statistics["governance_enforce_mean"] < h2.statistics[
        "governance_passive_mean"
    ]
    assert h2.statistics["governance_passive_mean"] < h2.statistics[
        "governance_baseline_mean"
    ]


def test_h2_rejects_when_passive_is_not_between_baseline_and_enforce(
    tmp_path: Path,
):
    _, df = _prep(tmp_path)
    mask = (df["attack_axis"] == "governance") & (df["condition"] == "passive")
    df.loc[mask, "governance_violation_rate"] = 0.99

    [h2] = [r for r in evaluate_hypotheses(df) if r.hypothesis == "H2"]

    assert h2.verdict == "rejected", h2.summary


def test_h3_passes_on_fixture(tmp_path: Path):
    _, df = _prep(tmp_path)
    [h3] = [r for r in evaluate_hypotheses(df) if r.hypothesis == "H3"]
    # Fixture: TSR_passive=1.0, TSR_enforce=0.95 -> avg cost 0.05, worst 0.05.
    assert h3.verdict == "supported", h3.summary
    assert h3.statistics["avg_cost"] < 0.10
    assert h3.statistics["worst_cat_cost"] < 0.25


def test_h4_passes_on_fixture(tmp_path: Path):
    _, df = _prep(tmp_path)
    [h4] = [r for r in evaluate_hypotheses(df) if r.hypothesis == "H4"]
    # Vanilla-AA = 0.95 > SAF overall = 0.90 on every passive row.
    assert h4.verdict == "supported", h4.summary
    assert h4.statistics["frac_vaa_over_saf"] == 1.0
    assert h4.statistics["inference_chain_failure_rate"] > 0.0
    assert h4.statistics["identity_governance_failure_rate"] > 0.0


def test_h5_passes_on_fixture(tmp_path: Path):
    _, df = _prep(tmp_path)
    [h5] = [r for r in evaluate_hypotheses(df) if r.hypothesis == "H5"]
    # Composite under fixture: baseline ≈ -0.1, enforce ≈ +0.84. Every
    # model prefers enforce over baseline -> supported.
    assert h5.verdict == "supported", h5.summary


def test_render_markdown_report_has_every_section(tmp_path: Path):
    _, df = _prep(tmp_path)
    md = render_markdown_report(evaluate_hypotheses(df), version="v1.0.0")
    assert "# Pre-registration reconciliation — v1.0.0" in md
    for hyp in ("H1", "H2", "H3", "H4", "H5"):
        assert f"## {hyp}" in md
        assert md.count("Verdict:") >= 5


def test_reconcile_wide_reads_csv(tmp_path: Path):
    csv, _ = _prep(tmp_path)
    results = reconcile_wide(csv)
    assert len(results) == 5


def test_write_report_emits_markdown_file(tmp_path: Path):
    csv, _ = _prep(tmp_path)
    out = tmp_path / "v1.0.0" / "prereg_reconciliation.md"
    results = write_report(csv, out, version="v1.0.0")
    assert out.exists()
    assert out.read_text().startswith("# Pre-registration reconciliation — v1.0.0")
    assert len(results) == 5


def test_h4_inconclusive_when_vaa_absent(tmp_path: Path):
    # Rebuild without vanilla_aa_overall by stripping it post-hoc.
    import json

    root = build_synthetic_scorecards(tmp_path)
    for path in root.rglob("run_scorecard.json"):
        data = json.loads(path.read_text())
        dims = data.get("saf", {}).get("dims", {})
        dims.pop("vanilla_aa_overall", None)
        path.write_text(json.dumps(data))
    out = tmp_path / "long.csv"
    aggregate_to_csv(root, out)
    df = load_long_csv(out)
    [h4] = [r for r in evaluate_hypotheses(df) if r.hypothesis == "H4"]
    # After stripping vaa, column is NaN; verdict collapses to inconclusive.
    assert h4.verdict == "inconclusive"
