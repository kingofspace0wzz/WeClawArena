"""Synthetic scorecard fixtures for the Phase 6 analysis pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _scorecard(
    scenario_id: str,
    *,
    condition: str,
    model: str,
    saf_overall: float,
    privacy_leak: float = 0.0,
    security_asr: float = 0.0,
    tsr: float = 1.0,
    vanilla_aa_overall: float | None = None,
) -> dict:
    dims = {
        "recoverability": 1.0,
        "policy_checkability": 1.0,
        "attribution": 1.0,
        "evidence_integrity": 0.75,
        "phase_scoped_policy": 1.0,
    }
    if vanilla_aa_overall is not None:
        # H4 check looks for a ``vanilla_aa_overall`` SAF-family metric.
        dims["vanilla_aa_overall"] = vanilla_aa_overall
    return {
        "scenario_id": scenario_id,
        "saf": {
            "dims": dims,
            "passes": {
                "recoverability": True,
                "policy_checkability": True,
                "attribution": True,
                "evidence_integrity": False,
                "phase_scoped_policy": True,
            },
            "overall": saf_overall,
        },
        "task": {"tsr": tsr, "partial_credit": {}},
        "privacy": {"leak_rates": {"leak_rate": privacy_leak}},
        "security": {"asr": security_asr, "prop_depth": 0.0, "tiua": 1.0},
        "diagnostics": {},
        "evaluator_version": "eval_v1.0.0",
        "meta": {
            "condition": condition,
            "model": model,
            "seed": 0,
            "privacy_level": "L0",
        },
    }


@pytest.fixture
def synthetic_results_root(tmp_path: Path) -> Path:
    """Build a tmp root with 3 conditions × 2 models × 4 scenarios of scorecards.

    Conditions are engineered so that enforce < passive < baseline on both
    privacy leak rate and security ASR, giving stats tests a genuine shift
    to detect. SAF overall jumps from baseline (0.8) to passive/enforce (0.9)
    so model comparison tables see variance. H4 vanilla-AA overestimation is
    stamped by attaching ``vanilla_aa_overall`` higher than SAF overall in the
    passive condition.
    """
    root = tmp_path / "results"
    root.mkdir()
    configs = [
        ("baseline", "claude"),
        ("baseline", "gpt"),
        ("passive", "claude"),
        ("passive", "gpt"),
        ("enforce", "claude"),
        ("enforce", "gpt"),
    ]
    for cond, model in configs:
        for s in range(4):
            sid = f"sc-{s}"
            if cond == "baseline":
                privacy, security, saf_overall = 0.5, 0.4, 0.8
            elif cond == "passive":
                privacy, security, saf_overall = 0.2, 0.15, 0.9
            else:  # enforce
                privacy, security, saf_overall = 0.05, 0.03, 0.9
            vaa = 0.95 if cond == "passive" else None
            sc = _scorecard(
                sid,
                condition=cond,
                model=model,
                saf_overall=saf_overall,
                privacy_leak=privacy,
                security_asr=security,
                vanilla_aa_overall=vaa,
            )
            run_dir = root / f"{cond}-{model}-{sid}"
            run_dir.mkdir()
            (run_dir / "run_scorecard.json").write_text(json.dumps(sc))
    return root
