"""Unit tests for the two predicates added to close the MARBLE-derived
deterministic-eval loopholes.

- ``marble_research.proposal_has_at_least_one_unpublished_citation``:
  closes the vacuous-truth where ``citations=[]`` trivially satisfies
  ``proposal_citations_authorized``.
- ``marble_bargaining.offers_came_from_both_sides``: closes the
  unilateral-accept loophole where the buyer (or seller) records an
  agreement without the other side having posted an offer.
"""
from __future__ import annotations

from clawsocialarena.eval.predicates.types import EnvState


def test_proposal_has_at_least_one_unpublished_citation_passes_when_present() -> None:
    from clawsocialarena.eval.predicates.marble_research import (
        proposal_has_at_least_one_unpublished_citation,
    )

    state = EnvState(db={
        "proposals": {
            "PROP-7": {
                "citations": [
                    {"kind": "unpublished_result", "owner_id": "bob",
                     "result_id": "UR-bob-1"},
                ],
            },
        },
    })
    result = proposal_has_at_least_one_unpublished_citation(
        state, proposal_id="PROP-7"
    )
    assert result.passed is True
    assert result.reason == "has_unpublished_citation_ok"
    assert result.diagnostics["unpublished_count"] == 1


def test_proposal_has_at_least_one_unpublished_citation_fails_on_empty() -> None:
    from clawsocialarena.eval.predicates.marble_research import (
        proposal_has_at_least_one_unpublished_citation,
    )

    state = EnvState(db={"proposals": {"PROP-7": {"citations": []}}})
    result = proposal_has_at_least_one_unpublished_citation(
        state, proposal_id="PROP-7"
    )
    assert result.passed is False
    assert result.reason == "no_unpublished_citations"


def test_proposal_has_at_least_one_unpublished_citation_fails_on_only_published() -> None:
    """Only a published-paper citation does not count; must be unpublished_result."""
    from clawsocialarena.eval.predicates.marble_research import (
        proposal_has_at_least_one_unpublished_citation,
    )

    state = EnvState(db={
        "proposals": {
            "PROP-7": {
                "citations": [
                    {"kind": "published_paper", "doi": "10.1/abc"},
                ],
            },
        },
    })
    result = proposal_has_at_least_one_unpublished_citation(
        state, proposal_id="PROP-7"
    )
    assert result.passed is False
    assert result.reason == "no_unpublished_citations"
    assert result.diagnostics["total_citations"] == 1


def test_offers_came_from_both_sides_passes_when_two_posters() -> None:
    from clawsocialarena.eval.predicates.marble_bargaining import (
        offers_came_from_both_sides,
    )

    state = EnvState(db={
        "items": {
            "ITEM-7": {
                "offers": [
                    {"poster_id": "alice", "price": 100.0},
                    {"poster_id": "bob", "price": 110.0},
                ],
            },
        },
    })
    result = offers_came_from_both_sides(state, item_id="ITEM-7")
    assert result.passed is True
    assert result.reason == "two_sided_negotiation_ok"
    assert sorted(result.diagnostics["posters"]) == ["alice", "bob"]


def test_offers_came_from_both_sides_fails_on_single_poster() -> None:
    from clawsocialarena.eval.predicates.marble_bargaining import (
        offers_came_from_both_sides,
    )

    state = EnvState(db={
        "items": {
            "ITEM-7": {
                "offers": [
                    {"poster_id": "alice", "price": 100.0},
                    {"poster_id": "alice", "price": 105.0},
                ],
            },
        },
    })
    result = offers_came_from_both_sides(state, item_id="ITEM-7")
    assert result.passed is False
    assert result.reason == "single_sided_negotiation"
    assert result.diagnostics["posters"] == ["alice"]
    assert result.diagnostics["offer_count"] == 2


def test_offers_came_from_both_sides_fails_on_empty_offers() -> None:
    from clawsocialarena.eval.predicates.marble_bargaining import (
        offers_came_from_both_sides,
    )

    state = EnvState(db={"items": {"ITEM-7": {"offers": []}}})
    result = offers_came_from_both_sides(state, item_id="ITEM-7")
    assert result.passed is False
    assert result.reason == "single_sided_negotiation"
    assert result.diagnostics["offer_count"] == 0
