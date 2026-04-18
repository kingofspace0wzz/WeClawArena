"""Phase F / Task F4: scorecard v2 schema tests."""

from __future__ import annotations

import json

from clawsocialarena.eval.scorecard import (
    RunScorecard,
    SAFDimsPayload,
)


def _minimal_saf() -> SAFDimsPayload:
    return SAFDimsPayload(
        dims={
            "recoverability": 1.0,
            "policy_checkability": 1.0,
            "attribution": 1.0,
            "evidence_integrity": 1.0,
            "phase_scoped_policy": 1.0,
        },
        passes={
            "recoverability": True,
            "policy_checkability": True,
            "attribution": True,
            "evidence_integrity": True,
            "phase_scoped_policy": True,
        },
        overall=1.0,
    )


def test_v2_scorecard_carries_new_fields():
    sc = RunScorecard(
        scenario_id="scen-1",
        saf=_minimal_saf(),
        gateway_invariant_passed=False,
        cassette_hash="deadbeef" * 8,
        live_or_replay="replay",
        episode_graph_id="graph-1",
    )
    assert sc.gateway_invariant_passed is False
    assert sc.cassette_hash == "deadbeef" * 8
    assert sc.live_or_replay == "replay"
    assert sc.episode_graph_id == "graph-1"


def test_v2_scorecard_defaults():
    sc = RunScorecard(scenario_id="scen-1", saf=_minimal_saf())
    assert sc.gateway_invariant_passed is True
    assert sc.cassette_hash == ""
    assert sc.live_or_replay == "live"
    assert sc.episode_graph_id is None


def test_v2_scorecard_json_roundtrip():
    original = RunScorecard(
        scenario_id="scen-1",
        saf=_minimal_saf(),
        gateway_invariant_passed=False,
        cassette_hash="abc123",
        live_or_replay="replay",
        episode_graph_id="graph-2",
    )
    blob = original.model_dump_json()
    rebuilt = RunScorecard.model_validate_json(blob)
    assert rebuilt == original


def test_v1_dict_is_readable_via_from_v1_dict():
    v1_blob = {
        "scenario_id": "scen-old",
        "saf": {
            "dims": {
                "recoverability": 0.9,
                "policy_checkability": 1.0,
                "attribution": 0.75,
                "evidence_integrity": 0.8,
                "phase_scoped_policy": 1.0,
            },
            "passes": {
                "recoverability": True,
                "policy_checkability": True,
                "attribution": True,
                "evidence_integrity": True,
                "phase_scoped_policy": True,
            },
            "overall": 0.87,
        },
        "task": {"tsr": 1.0, "partial_credit": {}},
        "privacy": {"leak_rates": {}},
        "security": {"asr": 0.0, "prop_depth": 0.0, "tiua": 1.0},
        "diagnostics": {},
        "evaluator_version": "eval_v1.0.0",
        "meta": {},
    }
    sc = RunScorecard.from_v1_dict(v1_blob)
    # v2 fields filled with sensible defaults.
    assert sc.gateway_invariant_passed is True
    assert sc.cassette_hash == ""
    assert sc.live_or_replay == "live"
    assert sc.episode_graph_id is None
    # Original v1 fields preserved.
    assert sc.scenario_id == "scen-old"
    assert sc.saf.overall == 0.87
    assert sc.evaluator_version == "eval_v1.0.0"


def test_from_v1_dict_preserves_existing_v2_fields_when_present():
    """Idempotent: already-v2 dict passed through from_v1_dict round-trips
    without losing the v2 fields the dict already set."""

    v2_blob = {
        "scenario_id": "scen-new",
        "saf": {
            "dims": {
                "recoverability": 1.0,
                "policy_checkability": 1.0,
                "attribution": 1.0,
                "evidence_integrity": 1.0,
                "phase_scoped_policy": 1.0,
            },
            "passes": {
                "recoverability": True,
                "policy_checkability": True,
                "attribution": True,
                "evidence_integrity": True,
                "phase_scoped_policy": True,
            },
            "overall": 1.0,
        },
        "gateway_invariant_passed": False,
        "cassette_hash": "feedface",
        "live_or_replay": "replay",
        "episode_graph_id": "graph-2",
    }
    sc = RunScorecard.from_v1_dict(v2_blob)
    assert sc.gateway_invariant_passed is False
    assert sc.cassette_hash == "feedface"
    assert sc.live_or_replay == "replay"
    assert sc.episode_graph_id == "graph-2"


def test_evaluator_version_v2_is_default():
    sc = RunScorecard(scenario_id="scen-1", saf=_minimal_saf())
    assert sc.evaluator_version == "eval_v2.0.0"


def test_from_v1_dict_tags_missing_evaluator_version_as_v1():
    v1_blob_no_version = {
        "scenario_id": "scen-old",
        "saf": {
            "dims": {
                "recoverability": 1.0,
                "policy_checkability": 1.0,
                "attribution": 1.0,
                "evidence_integrity": 1.0,
                "phase_scoped_policy": 1.0,
            },
            "passes": {
                "recoverability": True,
                "policy_checkability": True,
                "attribution": True,
                "evidence_integrity": True,
                "phase_scoped_policy": True,
            },
            "overall": 1.0,
        },
    }
    sc = RunScorecard.from_v1_dict(v1_blob_no_version)
    assert sc.evaluator_version == "eval_v1.0.0"


def test_live_or_replay_literal_rejects_invalid_value():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RunScorecard(
            scenario_id="scen-1",
            saf=_minimal_saf(),
            live_or_replay="bogus",  # type: ignore[arg-type]
        )


def test_v2_scorecard_json_is_deterministic():
    """Same inputs twice -> byte-identical JSON."""

    sc1 = RunScorecard(
        scenario_id="s",
        saf=_minimal_saf(),
        cassette_hash="abc",
        episode_graph_id="g",
    )
    sc2 = RunScorecard(
        scenario_id="s",
        saf=_minimal_saf(),
        cassette_hash="abc",
        episode_graph_id="g",
    )
    assert sc1.model_dump_json() == sc2.model_dump_json()


def test_v1_dict_without_new_fields_produces_valid_json():
    """End-to-end: v1 JSON -> v2 RunScorecard -> v2 JSON round-trip."""

    v1_text = json.dumps(
        {
            "scenario_id": "scen-1",
            "saf": _minimal_saf().model_dump(),
            "evaluator_version": "eval_v1.0.0",
        }
    )
    sc = RunScorecard.from_v1_dict(json.loads(v1_text))
    # Serializes without crashing and contains the new fields with defaults.
    v2_text = sc.model_dump_json()
    v2_parsed = json.loads(v2_text)
    assert v2_parsed["gateway_invariant_passed"] is True
    assert v2_parsed["live_or_replay"] == "live"
