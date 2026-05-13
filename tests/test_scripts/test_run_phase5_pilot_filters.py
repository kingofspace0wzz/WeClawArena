"""Tests for --filter on run_phase5_pilot.py."""
from __future__ import annotations

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
