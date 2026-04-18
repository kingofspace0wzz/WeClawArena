"""Tests for the Phase G4 cost tracking: rates.yaml + cost.csv wiring."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
import yaml

from clawsocialarena.experiments.rates import (
    RateEntry,
    estimate_cost_usd,
    get_rate,
)
from scripts import run_grid


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_CASSETTE = (
    REPO_ROOT / "fixtures" / "scenarios" / "cu_scheduling_mvp" / "sample_cassette.jsonl"
)


def test_rates_yaml_has_four_panel_models() -> None:
    """Spec §5.2 mandates the four-provider panel; rates must cover it."""

    for model in ("claude-sonnet-4-6", "gpt-5-mini", "deepseek-v3", "qwen3-72b-instruct"):
        rate = get_rate(model)
        assert isinstance(rate, RateEntry)
        assert rate.input_usd_per_m > 0
        assert rate.output_usd_per_m > 0


def test_unknown_model_is_zero_rate() -> None:
    """Missing rate entries must not crash the runner."""

    rate = get_rate("fictional-model-xyz")
    assert rate == RateEntry(0.0, 0.0, 0.0)
    assert estimate_cost_usd(
        model="fictional-model-xyz",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cached_tokens=1_000_000,
    ) == 0.0


def test_cost_calculation_matches_hand_computed_value() -> None:
    """Sanity check the dollars-per-million arithmetic.

    1,000,000 input + 1,000,000 output tokens for claude-sonnet-4-6 at
    $3 / $15 per million should land at exactly $18.
    """

    rate = get_rate("claude-sonnet-4-6")
    expected = rate.input_usd_per_m + rate.output_usd_per_m
    got = estimate_cost_usd(
        model="claude-sonnet-4-6",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cached_tokens=0,
    )
    assert got == pytest.approx(expected)


def test_cached_tokens_use_cached_rate() -> None:
    """Cached tokens must be priced at the cached-input rate, not the input rate."""

    rate = get_rate("claude-sonnet-4-6")
    got = estimate_cost_usd(
        model="claude-sonnet-4-6",
        input_tokens=0,
        output_tokens=0,
        cached_tokens=1_000_000,
    )
    assert got == pytest.approx(rate.cached_input_usd_per_m)


def test_cost_csv_written_for_dry_run_rows(tmp_path: Path) -> None:
    """Dry-run rows contribute zero-cost entries to cost.csv."""

    rows = [
        {
            "scenario_id": "cu-scheduling-mvp",
            "condition": "passive",
            "model": "claude-sonnet-4-6",
            "privacy_level": "L2",
            "seed": 0,
            "live_or_replay": "live",
        },
        {
            "scenario_id": "cu-scheduling-mvp",
            "condition": "enforce",
            "model": "gpt-5-mini",
            "privacy_level": "L2",
            "seed": 0,
            "live_or_replay": "live",
        },
    ]
    grid = tmp_path / "grid.yaml"
    grid.write_text(yaml.safe_dump(rows, sort_keys=False), encoding="utf-8")
    out = tmp_path / "results"
    run_grid.main(["--config", str(grid), "--out", str(out), "--dry-run"])

    cost_csv = out / "cost.csv"
    assert cost_csv.exists()
    with cost_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        records = list(reader)

    assert len(records) == 2
    for rec in records:
        assert rec["input_tokens"] == "0"
        assert rec["output_tokens"] == "0"
        assert rec["cached_tokens"] == "0"
        assert float(rec["estimated_cost_usd"]) == 0.0
        assert set(rec.keys()) == set(run_grid.COST_CSV_FIELDS)


def test_cost_csv_written_for_replay_row(tmp_path: Path) -> None:
    """Replay rows land a zero-cost entry (LLM was never invoked)."""

    rows = [
        {
            "scenario_id": "cu-scheduling-mvp",
            "condition": "passive",
            "model": "claude-sonnet-4-6",
            "privacy_level": "L2",
            "seed": 0,
            "live_or_replay": "replay",
            "cassette_path": str(SAMPLE_CASSETTE),
        },
    ]
    grid = tmp_path / "grid.yaml"
    grid.write_text(yaml.safe_dump(rows, sort_keys=False), encoding="utf-8")
    out = tmp_path / "results"
    rc = run_grid.main(["--config", str(grid), "--out", str(out)])
    assert rc == 0

    cost_csv = out / "cost.csv"
    assert cost_csv.exists()
    with cost_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        records = list(reader)

    assert len(records) == 1
    rec = records[0]
    assert rec["scenario_id"] == "cu-scheduling-mvp"
    assert rec["condition"] == "passive"
    assert rec["model"] == "claude-sonnet-4-6"
    # Replay rows never invoked an LLM, so every token column is zero.
    assert rec["input_tokens"] == "0"
    assert rec["output_tokens"] == "0"
    assert rec["cached_tokens"] == "0"
    assert float(rec["estimated_cost_usd"]) == 0.0
    # Wallclock is a positive float (the replay took some non-zero time).
    assert float(rec["wallclock_seconds"]) >= 0.0


def test_aggregate_llm_call_tokens_from_records() -> None:
    """Standalone aggregator sums llm_call records and ignores everything else."""

    class FakeRec:
        def __init__(self, kind: str, payload: dict):
            # emulate the .value attribute on ActionType.
            class _AT:
                def __init__(self, v):
                    self.value = v

            self.action_type = _AT(kind)
            self.payload = payload

    records = [
        FakeRec("llm_call", {"input_tokens": 100, "output_tokens": 50, "cached_tokens": 20}),
        FakeRec("outbound_message", {"content": "hi"}),  # ignored
        FakeRec("llm_call", {"input_tokens": 200, "output_tokens": 75, "cached_tokens": 10}),
        FakeRec("llm_call", {}),  # missing fields → zeros
    ]
    inp, out, cached = run_grid._aggregate_llm_call_tokens(records)
    assert inp == 300
    assert out == 125
    assert cached == 30


def test_cost_csv_header_is_stable(tmp_path: Path) -> None:
    """The column order must match COST_CSV_FIELDS exactly for pandas loaders."""

    rows = [
        {
            "scenario_id": "cu-scheduling-mvp",
            "condition": "passive",
            "model": "claude-sonnet-4-6",
            "privacy_level": "L2",
            "seed": 0,
            "live_or_replay": "live",
        },
    ]
    grid = tmp_path / "grid.yaml"
    grid.write_text(yaml.safe_dump(rows, sort_keys=False), encoding="utf-8")
    out = tmp_path / "r"
    run_grid.main(["--config", str(grid), "--out", str(out), "--dry-run"])
    header = (out / "cost.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == run_grid.COST_CSV_FIELDS
