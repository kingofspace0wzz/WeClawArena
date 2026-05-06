"""Aggregator v2 contract — wide-format, one-row-per-scorecard output."""

from __future__ import annotations

import csv
from pathlib import Path

from clawsocialarena.analysis.aggregator import (
    WIDE_FIELDS,
    aggregate_to_csv,
    scorecard_to_wide_row,
)

from tests.test_analysis.fixtures import build_synthetic_scorecards


def _count_rows(csv_path: Path) -> int:
    with csv_path.open() as f:
        return sum(1 for _ in csv.DictReader(f))


def test_wide_csv_has_one_row_per_scorecard(tmp_path: Path):
    root = build_synthetic_scorecards(tmp_path)
    out = tmp_path / "long.csv"

    n = aggregate_to_csv(root, out)
    # 4 models × 3 conditions × 4 attack axes × 3 scenarios = 144 rows.
    assert n == 144
    assert _count_rows(out) == 144


def test_wide_csv_header_has_all_phase_h_columns(tmp_path: Path):
    root = build_synthetic_scorecards(tmp_path)
    out = tmp_path / "long.csv"
    aggregate_to_csv(root, out)
    header = out.read_text().splitlines()[0].split(",")
    for col in (
        "scenario_id",
        "category",
        "family",
        "attack_axis",
        "attack_type",
        "model",
        "condition",
        "privacy_level",
        "seed",
        "live_or_replay",
        "tsr",
        "psi",
        "tau",
        "sigma",
        "phi",
        "gamma",
        "s",
        "saf_overall",
        "recoverability",
        "policy_checkability",
        "attribution",
        "evidence_integrity",
        "phase_scoped_policy",
        "identity_governance",
        "cdlr",
        "culr",
        "mplr",
        "halr",
        "cslr",
        "asr",
        "governance_violation_rate",
    ):
        assert col in header, f"missing column: {col}"
    # Fields list + header should agree 1:1.
    assert header == list(WIDE_FIELDS)


def test_wide_csv_carries_live_or_replay(tmp_path: Path):
    root = build_synthetic_scorecards(tmp_path, live_fraction=0.5)
    out = tmp_path / "long.csv"
    aggregate_to_csv(root, out)
    with out.open() as f:
        rows = list(csv.DictReader(f))
    labels = {r["live_or_replay"] for r in rows}
    assert labels == {"live", "replay"}


def test_wide_csv_skips_pending_stubs(tmp_path: Path):
    root = build_synthetic_scorecards(tmp_path, include_pending=True)
    out = tmp_path / "long.csv"
    n = aggregate_to_csv(root, out)
    # 144 real rows + 1 pending stub on disk -> 144 in the CSV.
    assert n == 144
    with out.open() as f:
        rows = list(csv.DictReader(f))
    assert "sc-pending" not in {r["scenario_id"] for r in rows}


def test_scorecard_to_wide_row_numeric_types(tmp_path: Path):
    root = build_synthetic_scorecards(
        tmp_path, models=("claude-sonnet-4-6",), conditions=("passive",)
    )
    # The factory wrote one scorecard per (model, condition, attack axis, scenario).
    one = next(iter(root.rglob("run_scorecard.json")))
    import json

    row = scorecard_to_wide_row(json.loads(one.read_text()))
    # Numeric fields must round-trip as floats/ints, not strings.
    for name in (
        "tsr",
        "psi",
        "tau",
        "sigma",
        "phi",
        "gamma",
        "s",
        "saf_overall",
        "recoverability",
        "policy_checkability",
        "attribution",
        "evidence_integrity",
        "phase_scoped_policy",
        "identity_governance",
        "asr",
        "governance_violation_rate",
    ):
        assert isinstance(row[name], float), f"{name!r} was {type(row[name]).__name__}"
    assert row["gamma"] == row["identity_governance"]
    assert isinstance(row["seed"], int)
    assert isinstance(row["gateway_invariant_passed"], bool)


def test_aggregate_captures_category_and_family(tmp_path: Path):
    root = build_synthetic_scorecards(tmp_path)
    out = tmp_path / "long.csv"
    aggregate_to_csv(root, out)
    with out.open() as f:
        rows = list(csv.DictReader(f))
    cats = {r["category"] for r in rows}
    fams = {r["family"] for r in rows}
    axes = {r["attack_axis"] for r in rows}
    attack_types = {r["attack_type"] for r in rows}
    assert cats == {"CD", "CU", "HS", "MC"}
    assert fams == {"coordination", "delegation", "governance", "privacy"}
    assert axes == {"collaboration", "security", "privacy", "governance"}
    assert "approval_bypass" in attack_types


def test_scorecard_to_wide_row_defaults_missing_governance_metrics_to_zero(
    tmp_path: Path,
):
    root = build_synthetic_scorecards(
        tmp_path, models=("claude-sonnet-4-6",), conditions=("passive",)
    )
    import json

    one = next(iter(root.rglob("run_scorecard.json")))
    scorecard = json.loads(one.read_text())
    scorecard.pop("governance", None)

    row = scorecard_to_wide_row(scorecard)

    assert row["governance_violation_rate"] == 0.0
    assert row["approval_bypass_rate"] == 0.0
