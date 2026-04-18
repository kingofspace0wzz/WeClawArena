"""Synthetic v2 scorecard fixtures for Phase H analysis tests.

Builds a ``results/<version>/<model>/<condition>/<scenario_id>/run_scorecard.json``
directory tree that matches the v2 scorecard schema
(:class:`clawsocialarena.eval.scorecard.RunScorecard`) and carries the
``tags`` provenance fields (``category``, ``family``, ``live_or_replay``)
that the Phase H analysis pipeline keys on.

The factory is used from every Phase H test: it is not a pytest fixture
in the classic sense but a plain helper callable so tests can control
``version``, ``models``, ``categories``, etc. individually.

Scenario generation is deterministic and deliberately engineered so that
the resulting distributions contain a genuine condition effect:

    - baseline:  TSR=1.0,  privacy leak ≈ 0.50,  ASR ≈ 0.40,  SAF ≈ 0.80
    - passive :  TSR=1.0,  privacy leak ≈ 0.20,  ASR ≈ 0.15,  SAF ≈ 0.90
    - enforce :  TSR=0.9,  privacy leak ≈ 0.05,  ASR ≈ 0.03,  SAF ≈ 0.92

That lets Wilcoxon tests detect the shift without being a pure constant
and lets the rewrite-quality table observe a nonzero ``enforce - passive``
delta on the TSR axis.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


DEFAULT_MODELS: tuple[str, ...] = (
    "claude-sonnet-4-6",
    "gpt-5-mini",
    "gemini-2-5-flash",
    "llama-4-maverick",
)
DEFAULT_CONDITIONS: tuple[str, ...] = ("baseline", "passive", "enforce")
DEFAULT_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("CD", "auditability"),
    ("MC", "privacy"),
)
SCENARIOS_PER_CATEGORY = 1
"""Phase H asks for 20-30 scorecards across 4 models × 3 conditions × 2
categories × 3 scenarios. The default grid samples the {model, condition,
category} axes exhaustively at one scenario per cell, landing on 24 rows.
Tests that need denser coverage can pass ``scenarios_per_category=3``."""


@dataclass(frozen=True)
class _ScorecardSpec:
    scenario_id: str
    category: str
    family: str
    model: str
    condition: str
    seed: int
    live_or_replay: str


_SAF_DIM_NAMES = (
    "recoverability",
    "policy_checkability",
    "attribution",
    "evidence_integrity",
    "phase_scoped_policy",
)

# Per-dim nudge applied to ``saf_overall`` when synthesising dims. Tuned so
# that attribution (τ) and phase_scoped_policy (φ) are the two lowest SAF
# dimensions under passive — matching H1's pre-registered prediction.
_SAF_DIM_NUDGES: dict[str, float] = {
    "recoverability": 0.05,
    "policy_checkability": 0.03,
    "attribution": -0.05,  # τ -- weakest under H1.
    "evidence_integrity": 0.02,
    "phase_scoped_policy": -0.03,  # φ -- second-weakest under H1.
}


def _condition_profile(condition: str) -> dict[str, float]:
    """Return the base metric profile per condition.

    Values chosen so that enforce < passive < baseline on privacy + security
    and enforce takes a modest TSR hit vs passive — exactly the shape the
    pre-registered H2/H3 checks expect.
    """

    if condition == "baseline":
        return {
            "saf_overall": 0.80,
            "privacy_leak": 0.50,
            "security_asr": 0.40,
            "tsr": 1.0,
        }
    if condition == "passive":
        return {
            "saf_overall": 0.90,
            "privacy_leak": 0.20,
            "security_asr": 0.15,
            "tsr": 1.0,
        }
    # enforce
    return {
        "saf_overall": 0.92,
        "privacy_leak": 0.05,
        "security_asr": 0.03,
        # TSR cost under enforce is bounded: 0.05 average (< 10%). This
        # lets H3 flip ``supported`` on the synthetic fixture, matching
        # the spec's ``<10% average, <25% worst-case per category`` bound.
        "tsr": 0.95,
    }


def _leak_rates(category: str, family: str, leak: float) -> dict[str, float]:
    """Family-specific leak-rate dictionary stamped into ``privacy.leak_rates``.

    Keys match the per-category verifiable variants named in spec §5.2
    (``CDLR``/``CULR``/``MPLR``/``HALR``/``CSLR``). Passing a flat
    ``leak_rate`` in addition lets legacy tests (``test_stats.py``) keep
    using ``metric_name="leak_rate"`` unchanged.
    """

    # Base keys present on every scenario (the H2 verdict reads flat ``leak_rate``).
    rates: dict[str, float] = {"leak_rate": leak}
    # Category-primary rate — a name chosen per category.
    primary = {
        "CD": "CDLR",
        "CU": "CULR",
        "MC": "MPLR",
        "HS": "HALR",
        "CS": "CSLR",
    }.get(category, f"{category}LR")
    rates[primary] = leak
    _ = family  # Currently only category gates the naming; kept for future variants.
    return rates


def _scorecard_dict(spec: _ScorecardSpec) -> dict:
    """Render one scorecard as a v2-shaped JSON dict.

    The structure is *exactly* what
    :meth:`clawsocialarena.eval.scorecard.RunScorecard.model_validate`
    accepts (plus the ``tags`` convention we rely on downstream).
    """

    profile = _condition_profile(spec.condition)
    leak = profile["privacy_leak"]
    asr = profile["security_asr"]
    saf_overall = profile["saf_overall"]
    tsr = profile["tsr"]

    # Per-dim scores nudge around ``saf_overall`` so that τ (attribution) and
    # φ (phase_scoped_policy) sit lowest — mirroring H1's prediction.
    dims = {
        name: round(max(0.0, min(1.0, saf_overall + _SAF_DIM_NUDGES[name])), 4)
        for name in _SAF_DIM_NAMES
    }
    passes = {name: v >= 0.80 for name, v in dims.items()}

    # H4 check: vanilla-AA overestimates auditability on the passive condition.
    if spec.condition == "passive":
        dims["vanilla_aa_overall"] = round(saf_overall + 0.05, 4)

    return {
        "scenario_id": spec.scenario_id,
        "saf": {
            "dims": dims,
            "passes": passes,
            "overall": saf_overall,
        },
        "task": {"tsr": tsr, "partial_credit": {}},
        "privacy": {
            "leak_rates": _leak_rates(spec.category, spec.family, leak),
        },
        "security": {"asr": asr, "prop_depth": 0.1 * asr, "tiua": 1.0 - asr},
        "diagnostics": {
            "error_chains": {"L0": 0, "L1": 0, "LX": 0, "LR": 0, "LF": 0},
        },
        "evaluator_version": "eval_v2.0.0",
        "meta": {
            "condition": spec.condition,
            "model": spec.model,
            "seed": spec.seed,
            "privacy_level": "L0",
            "live_or_replay": spec.live_or_replay,
            "tags": {
                "category": spec.category,
                "family": spec.family,
                "bucket": "main_table",
            },
        },
        "gateway_invariant_passed": True,
        "cassette_hash": "deadbeef" * 8,
        "live_or_replay": spec.live_or_replay,
        "episode_graph_id": None,
    }


def build_synthetic_scorecards(
    root: Path,
    *,
    version: str = "v1.0.0",
    models: Sequence[str] = DEFAULT_MODELS,
    conditions: Sequence[str] = DEFAULT_CONDITIONS,
    categories: Sequence[tuple[str, str]] = DEFAULT_CATEGORIES,
    scenarios_per_category: int = SCENARIOS_PER_CATEGORY,
    live_fraction: float = 1.0 / 3.0,
    include_pending: bool = False,
) -> Path:
    """Materialize a synthetic v2 scorecard tree on disk and return its root.

    Arguments:
        root: Parent directory; the real tree lives under ``root/<version>``.
        version: Results version label (matches spec §6 ``eval_vN.M.P``).
        models, conditions, categories: The grid axes (category is a pair
            of ``(category_code, family_label)``).
        scenarios_per_category: Scenarios generated per category.
        live_fraction: Fraction of scorecards tagged ``live_or_replay="live"``.
        include_pending: If True, also drops a ``status: "pending"`` stub
            beneath the tree so aggregator tests can verify the skip path.

    Layout:
        ``root/<version>/<model>/<condition>/<scenario_id>/run_scorecard.json``
    """

    out = root / version
    out.mkdir(parents=True, exist_ok=True)

    specs = list(_enumerate_specs(models, conditions, categories, scenarios_per_category, live_fraction))
    for spec in specs:
        path = out / spec.model / spec.condition / spec.scenario_id / "run_scorecard.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_scorecard_dict(spec), indent=2, sort_keys=True))

    if include_pending:
        stub_path = out / "pending_model" / "baseline" / "sc-pending" / "run_scorecard.json"
        stub_path.parent.mkdir(parents=True, exist_ok=True)
        stub_path.write_text(
            json.dumps(
                {
                    "scenario_id": "sc-pending",
                    "status": "pending",
                    "meta": {
                        "condition": "baseline",
                        "model": "pending_model",
                        "seed": 0,
                        "privacy_level": "L0",
                        "live_or_replay": "live",
                        "tags": {"category": "CD", "family": "auditability"},
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )

    return out


def _enumerate_specs(
    models: Sequence[str],
    conditions: Sequence[str],
    categories: Sequence[tuple[str, str]],
    scenarios_per_category: int,
    live_fraction: float,
) -> Iterable[_ScorecardSpec]:
    """Cartesian product of (model, condition, category, scenario) specs.

    ``live_or_replay`` is pinned per (model, category, scenario) triple so
    every condition for the same scenario/model pair carries the same
    strata label. Without that, the pairwise rewrite-quality delta loses
    rows because the same scenario appears under ``live`` for one
    condition and ``replay`` for another.
    """

    step = max(1, int(round(1.0 / max(live_fraction, 1e-6))))

    # Pre-compute the strata label for every (model, cat, scenario) cell.
    strata: dict[tuple[str, str, int], str] = {}
    index = 0
    for model in models:
        for cat, _fam in categories:
            for s in range(scenarios_per_category):
                strata[(model, cat, s)] = "live" if index % step == 0 else "replay"
                index += 1

    for model in models:
        for condition in conditions:
            for cat, fam in categories:
                for s in range(scenarios_per_category):
                    sid = f"{cat}-{fam}-{s}"
                    yield _ScorecardSpec(
                        scenario_id=sid,
                        category=cat,
                        family=fam,
                        model=model,
                        condition=condition,
                        seed=s,
                        live_or_replay=strata[(model, cat, s)],
                    )


def default_synthetic_tree(root: Path) -> Path:
    """Shortcut used from pytest fixtures: builds the default grid.

    Returns the scorecard root (``root/v1.0.0``). The default grid holds
    4 models × 3 conditions × 2 categories × 3 scenarios = 72 rows, well
    above the 20-30 scorecard minimum the Phase H plan asks for while
    still staying cheap to materialize on disk.
    """

    return build_synthetic_scorecards(root)
