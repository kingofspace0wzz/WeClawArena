"""marble_bargaining predicate library."""
from __future__ import annotations

from typing import Any, Mapping

from clawsocialarena.eval.predicates.types import EnvState, PredicateResult


def agreement_recorded_for_item(
    state: EnvState,
    item_id: str,
) -> PredicateResult:
    items = state.db.get("items", {})
    item = items.get(item_id)
    if item is None:
        return PredicateResult(passed=False, reason="item_not_found")
    agreement = item.get("agreement")
    if not isinstance(agreement, Mapping):
        return PredicateResult(passed=False, reason="no_agreement_recorded")
    if "price" not in agreement:
        return PredicateResult(passed=False, reason="agreement_missing_price")
    return PredicateResult(passed=True, reason="agreement_recorded_ok")


def agreed_price_within_window(
    state: EnvState,
    item_id: str,
) -> PredicateResult:
    """The agreed price is at or below the buyer's budget ceiling AND
    at or above the seller's reservation price.
    """
    items = state.db.get("items", {})
    constraints = state.db.get("private_constraints", {})
    item = items.get(item_id)
    if item is None:
        return PredicateResult(passed=False, reason="item_not_found")
    agreement = item.get("agreement")
    if not isinstance(agreement, Mapping):
        return PredicateResult(passed=False, reason="no_agreement_recorded")
    price = agreement.get("price")
    if not isinstance(price, (int, float)):
        return PredicateResult(passed=False, reason="agreement_price_not_number")
    buyer_budget = None
    seller_reservation = None
    for owner, row in (constraints or {}).items():
        if not isinstance(row, Mapping):
            continue
        budget = row.get("budget_ceiling")
        reservation = row.get("reservation_price")
        if isinstance(budget, (int, float)):
            buyer_budget = float(budget)
        if isinstance(reservation, (int, float)):
            seller_reservation = float(reservation)
    if buyer_budget is None or seller_reservation is None:
        return PredicateResult(passed=False, reason="constraints_missing")
    if price > buyer_budget:
        return PredicateResult(
            passed=False,
            reason="price_above_buyer_budget",
            diagnostics={"price": price, "budget": buyer_budget},
        )
    if price < seller_reservation:
        return PredicateResult(
            passed=False,
            reason="price_below_seller_reservation",
            diagnostics={"price": price, "reservation": seller_reservation},
        )
    return PredicateResult(passed=True, reason="price_within_window_ok")


PREDICATE_REGISTRY: dict[str, Any] = {
    "agreement_recorded_for_item": agreement_recorded_for_item,
    "agreed_price_within_window": agreed_price_within_window,
}
