import math
import pytest

from clawsocialarena.audit.phase_tracker import PhaseTracker
from clawsocialarena.audit.policy_registry import PolicyRegistry
from clawsocialarena.saf.saf_scorer import SAFScorer, SAFScorecard
from clawsocialarena.scenario.models import GTBundle


def test_geometric_mean_equal_weights():
    subs = {"a": 1.0, "b": 0.5}
    m = SAFScorer.geometric_mean(subs, weights={"a": 0.5, "b": 0.5})
    # sqrt(1 * 0.5) ~= 0.7071
    assert abs(m - math.sqrt(0.5)) < 1e-9


def test_geometric_mean_zero_collapses():
    subs = {"a": 1.0, "b": 0.0}
    m = SAFScorer.geometric_mean(subs, weights={"a": 0.5, "b": 0.5})
    assert m == 0.0


def test_saf_scorer_produces_scorecard_with_all_dims():
    gt = GTBundle(
        scenario_id="test",
        canonical_action_stream=[],
        phase_schedule=[],
        policies={"flat": [], "phase_scoped": []},
        attribution_dag={"nodes": [], "edges": []},
        integrity_requirements={},
        terminal_predicate={"type": "none"},
        invariants={},
        attack_plan=None,
    )
    scorer = SAFScorer(policy_registry=PolicyRegistry(), phase_tracker=PhaseTracker())
    card: SAFScorecard = scorer.score(
        action_log=[], shadow_log=[],
        produced_dag={"nodes": [], "edges": []}, gt=gt,
    )
    # All 5 dimensions should be present
    expected_dims = {
        "recoverability",
        "policy_checkability",
        "attribution",
        "evidence_integrity",
        "phase_scoped_policy",
    }
    assert set(card.dims.keys()) == expected_dims
    assert set(card.passes.keys()) == expected_dims
    # With empty inputs + no requirements, every dim is 1.0
    assert all(v == 1.0 for v in card.dims.values())
    assert all(card.passes.values())
    assert card.overall == 1.0
