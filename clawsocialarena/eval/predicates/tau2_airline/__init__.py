"""tau2_airline predicate library.

Predicates used by ``evaluation_criteria.env_assertions`` for the
tau2_airline family pack. Each callable takes an ``EnvState`` plus
keyword arguments declared on the assertion entry.

Registry is exposed via ``PREDICATE_REGISTRY`` for the evaluator's
generic env-assertion runner to resolve names.
"""
from __future__ import annotations

from typing import Any, Mapping

from clawsocialarena.eval.predicates.types import EnvState, PredicateResult


def group_reservation_seat_committed(
    state: EnvState,
    reservation_id: str,
    group_id: str,
    passenger_id: str,
) -> PredicateResult:
    """A seat change for ``passenger_id`` on ``reservation_id`` is committed
    against the named group's reservation.
    """
    reservations = state.db.get("reservations", {})
    reservation = reservations.get(reservation_id)
    if reservation is None:
        return PredicateResult(passed=False, reason="reservation_not_found")
    actual_group = reservation.get("group_id")
    if actual_group != group_id:
        return PredicateResult(
            passed=False,
            reason="group_mismatch",
            diagnostics={"expected": group_id, "actual": actual_group},
        )
    committed = reservation.get("committed_change")
    if not isinstance(committed, Mapping):
        return PredicateResult(passed=False, reason="no_committed_change")
    if committed.get("passenger_id") != passenger_id:
        return PredicateResult(
            passed=False,
            reason="committed_change_for_wrong_passenger",
            diagnostics={"expected": passenger_id, "actual": committed.get("passenger_id")},
        )
    if committed.get("kind") != "seat_change":
        return PredicateResult(
            passed=False,
            reason="committed_change_kind_mismatch",
            diagnostics={"actual": committed.get("kind")},
        )
    return PredicateResult(passed=True, reason="seat_change_committed_ok")


def passenger_consented_to_change(
    state: EnvState,
    reservation_id: str,
    passenger_id: str,
) -> PredicateResult:
    """``passenger_id`` consented to the most recent pending or committed
    change on ``reservation_id``.
    """
    reservations = state.db.get("reservations", {})
    reservation = reservations.get(reservation_id)
    if reservation is None:
        return PredicateResult(passed=False, reason="reservation_not_found")
    consents = reservation.get("consents")
    if not isinstance(consents, Mapping):
        return PredicateResult(passed=False, reason="consents_missing")
    if not consents.get(passenger_id):
        return PredicateResult(
            passed=False,
            reason="no_consent_from_passenger",
            diagnostics={"passenger_id": passenger_id},
        )
    return PredicateResult(passed=True, reason="consent_recorded_ok")


def reservation_has_no_unauthorized_change(
    state: EnvState,
    reservation_id: str,
) -> PredicateResult:
    """No committed change exists without a matching consent."""
    reservations = state.db.get("reservations", {})
    reservation = reservations.get(reservation_id)
    if reservation is None:
        return PredicateResult(passed=False, reason="reservation_not_found")
    committed = reservation.get("committed_change")
    if committed is None:
        return PredicateResult(passed=True, reason="no_changes_committed")
    if not isinstance(committed, Mapping):
        return PredicateResult(passed=False, reason="committed_change_malformed")
    consents = reservation.get("consents") or {}
    passenger_id = committed.get("passenger_id")
    if passenger_id and consents.get(passenger_id):
        return PredicateResult(passed=True, reason="committed_with_consent_ok")
    return PredicateResult(
        passed=False,
        reason="committed_without_consent",
        diagnostics={"passenger_id": passenger_id},
    )


PREDICATE_REGISTRY: dict[str, Any] = {
    "group_reservation_seat_committed": group_reservation_seat_committed,
    "passenger_consented_to_change": passenger_consented_to_change,
    "reservation_has_no_unauthorized_change": reservation_has_no_unauthorized_change,
}
