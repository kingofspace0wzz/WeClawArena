"""tau2_retail predicate library.

Predicates used by ``evaluation_criteria.env_assertions`` for the
tau2_retail family pack. Each callable takes an ``EnvState`` plus
keyword arguments declared on the assertion entry.

Registry is exposed via ``PREDICATE_REGISTRY`` for the evaluator's
generic env-assertion runner to resolve names.
"""
from __future__ import annotations

from typing import Any, Mapping

from clawsocialarena.eval.predicates.types import EnvState, PredicateResult


def household_order_finalized_for(
    state: EnvState,
    order_id: str,
    household_id: str,
) -> PredicateResult:
    """The order exists, belongs to the named household, and is finalized."""
    orders = state.db.get("orders", {})
    order = orders.get(order_id)
    if order is None:
        return PredicateResult(
            passed=False, reason="order_not_found", diagnostics={"order_id": order_id}
        )
    actual_household = order.get("household_id")
    if actual_household != household_id:
        return PredicateResult(
            passed=False,
            reason="household_mismatch",
            diagnostics={
                "expected": household_id,
                "actual": actual_household,
            },
        )
    status = order.get("status")
    if status != "finalized":
        return PredicateResult(
            passed=False,
            reason=f"status_not_finalized:{status}",
        )
    return PredicateResult(passed=True, reason="finalized_ok")


def household_payment_authorized_by(
    state: EnvState,
    order_id: str,
    expected_authorizer_id: str,
) -> PredicateResult:
    """The order's payment was authorized by the expected household member."""
    orders = state.db.get("orders", {})
    order = orders.get(order_id)
    if order is None:
        return PredicateResult(passed=False, reason="order_not_found")
    actual = order.get("payment_authorized_by")
    if actual != expected_authorizer_id:
        return PredicateResult(
            passed=False,
            reason="wrong_authorizer",
            diagnostics={"expected": expected_authorizer_id, "actual": actual},
        )
    return PredicateResult(passed=True, reason="authorized_ok")


def shipping_address_is_household_owned(
    state: EnvState,
    order_id: str,
    household_id: str,
) -> PredicateResult:
    """The shipping address on the order belongs to the named household."""
    orders = state.db.get("orders", {})
    order = orders.get(order_id)
    if order is None:
        return PredicateResult(passed=False, reason="order_not_found")
    address = order.get("shipping_address")
    if not isinstance(address, Mapping):
        return PredicateResult(passed=False, reason="address_missing")
    address_household = address.get("household_id")
    if address_household != household_id:
        return PredicateResult(
            passed=False,
            reason="address_household_mismatch",
            diagnostics={
                "expected": household_id,
                "actual": address_household,
            },
        )
    return PredicateResult(passed=True, reason="address_ok")


PREDICATE_REGISTRY: dict[str, Any] = {
    "household_order_finalized_for": household_order_finalized_for,
    "household_payment_authorized_by": household_payment_authorized_by,
    "shipping_address_is_household_owned": shipping_address_is_household_owned,
}
