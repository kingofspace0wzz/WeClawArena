"""Tests for --filter on run_phase5_pilot.py."""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any


def _fake_manifest() -> dict[str, Any]:
    return {
        "rows": [
            {"variant_id": "x__no_attacker", "base_id": "x", "family_id": "tau2_telecom",
             "task_index": 0, "attack_mode": "no_attacker"},
            {"variant_id": "x__privacy", "base_id": "x", "family_id": "tau2_telecom",
             "task_index": 0, "attack_mode": "privacy"},
            {"variant_id": "y__no_attacker", "base_id": "y", "family_id": "tau2_retail",
             "task_index": 1, "attack_mode": "no_attacker"},
            {"variant_id": "y__privacy", "base_id": "y", "family_id": "tau2_retail",
             "task_index": 1, "attack_mode": "privacy"},
        ]
    }


def test_filter_parses_family_mode() -> None:
    from scripts.run_phase5_pilot import parse_filter_string, apply_filter

    flt = parse_filter_string("family=tau2_telecom,mode=privacy")
    assert flt == {"family": "tau2_telecom", "mode": "privacy"}
    rows = apply_filter(_fake_manifest()["rows"], flt)
    assert [r["variant_id"] for r in rows] == ["x__privacy"]


def test_filter_empty_returns_all() -> None:
    from scripts.run_phase5_pilot import parse_filter_string, apply_filter

    flt = parse_filter_string("")
    assert flt == {}
    rows = apply_filter(_fake_manifest()["rows"], flt)
    assert len(rows) == 4


def test_store_manifest_rows_are_exposed_as_main_rows() -> None:
    from scripts.run_phase5_pilot import normalize_store_manifest_for_batches

    manifest = normalize_store_manifest_for_batches(_fake_manifest())

    assert "main" in manifest
    assert manifest["main"] == _fake_manifest()["rows"]
    assert manifest["supplementary"] == []


def test_filtered_manifest_relaxes_batch_expected_rows() -> None:
    from clawsocialarena.orchestrator.phase5_run_batches import run_batch_for
    from scripts.run_phase5_pilot import (
        _apply_filter_to_manifest,
        _relax_batch_expected_rows_for_filtered_manifest,
        normalize_store_manifest_for_batches,
    )

    manifest = normalize_store_manifest_for_batches(_fake_manifest())
    filtered = _apply_filter_to_manifest(manifest, "family=tau2_telecom")
    spec = run_batch_for(2)
    original_expected_rows = spec.expected_rows
    original_alternatives = spec.expected_rows_alternatives
    try:
        _relax_batch_expected_rows_for_filtered_manifest(
            manifest=filtered,
            batch_number=2,
        )

        rows = spec.select(filtered)

        assert len(rows) == 2
        assert [row["variant_id"] for row in rows] == [
            "x__no_attacker",
            "x__privacy",
        ]
    finally:
        object.__setattr__(spec, "expected_rows", original_expected_rows)
        object.__setattr__(
            spec,
            "expected_rows_alternatives",
            original_alternatives,
        )


def test_docker_executor_receives_max_turns_override() -> None:
    from clawsocialarena.orchestrator.phase5_docker_executor import (
        DriverOrchestratedDockerExecutor,
    )
    from scripts.run_phase5_pilot import _select_executor

    executor = _select_executor(
        Namespace(
            executor="docker",
            store=Path("benchmark/scenarios/v2.0.0"),
            out_dir=Path("benchmark/phase5/pilot/test"),
            agent_model="gpt-4.1-mini",
            max_turns=50,
        )
    )

    assert isinstance(executor, DriverOrchestratedDockerExecutor)
    assert executor.max_turns_override == 50


def test_current_store_manifest_exposes_bidding_rows() -> None:
    import json

    from scripts.run_phase5_pilot import apply_filter, normalize_store_manifest_for_batches

    manifest_path = Path("benchmark/scenarios/v2.0.0/manifest.json")
    manifest = normalize_store_manifest_for_batches(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    bidding_rows = apply_filter(manifest["main"], {"family": "marble_bidding"})

    assert len(bidding_rows) == 60
    assert {
        row["attack_mode"] for row in bidding_rows
    } == {
        "collaboration",
        "governance",
        "no_attacker",
        "privacy",
        "security",
    }
