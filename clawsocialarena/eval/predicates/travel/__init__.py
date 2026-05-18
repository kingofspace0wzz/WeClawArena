"""Travel family predicate library.

The post-run EnvState merges every owner's sqlite db, so the
partner_hotel's ``seller_orders`` table (the only table that records
the closed booking) is visible by table-name lookup. Predicates pull
the row by ``trip_id`` and check structural integrity (hotel_id
non-empty and present in inventory) and bargaining-zone compliance
(unit_rate within the seed-declared ``[partner_floor_rate,
target_unit_rate]`` bounds). The bounds are passed in by the loader
when it builds ``evaluation_criteria.env_assertions`` so the
predicates do not have to look them up in the bundle.
"""
from __future__ import annotations

from typing import Any, Mapping

from clawsocialarena.eval.predicates.types import EnvState, PredicateResult


def _find_seller_order(state: EnvState, trip_id: str) -> Mapping[str, Any] | None:
    for row in state.db.get("seller_orders", {}).values():
        if isinstance(row, Mapping) and str(row.get("trip_id") or "") == trip_id:
            return row
    return None


def _find_inventory_hotel_ids(state: EnvState) -> set[str]:
    out: set[str] = set()
    for row in state.db.get("inventory", {}).values():
        if isinstance(row, Mapping):
            hid = row.get("hotel_id")
            if isinstance(hid, str) and hid:
                out.add(hid)
    return out


def unit_rate_in_zone(
    state: EnvState,
    trip_id: str,
    floor: float,
    target: float,
) -> PredicateResult:
    """Strict bargaining-zone check: floor <= seller_orders.unit_rate <= target."""
    order = _find_seller_order(state, trip_id)
    if order is None:
        return PredicateResult(
            passed=False,
            reason="seller_order_missing",
            diagnostics={"trip_id": trip_id},
        )
    raw = order.get("unit_rate")
    try:
        unit_rate = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        unit_rate = None
    if unit_rate is None:
        return PredicateResult(
            passed=False,
            reason="unit_rate_missing",
            diagnostics={"trip_id": trip_id, "raw_unit_rate": raw},
        )
    if unit_rate < float(floor):
        return PredicateResult(
            passed=False,
            reason="unit_rate_below_floor",
            diagnostics={"trip_id": trip_id, "unit_rate": unit_rate, "floor": float(floor)},
        )
    if unit_rate > float(target):
        return PredicateResult(
            passed=False,
            reason="unit_rate_above_target",
            diagnostics={"trip_id": trip_id, "unit_rate": unit_rate, "target": float(target)},
        )
    return PredicateResult(
        passed=True,
        reason="unit_rate_in_zone_ok",
        diagnostics={"trip_id": trip_id, "unit_rate": unit_rate,
                     "floor": float(floor), "target": float(target)},
    )


def hotel_id_present(
    state: EnvState,
    trip_id: str,
) -> PredicateResult:
    """``seller_orders.hotel_id`` for ``trip_id`` is non-empty and is a hotel
    that exists in the partner's ``inventory`` table.
    """
    order = _find_seller_order(state, trip_id)
    if order is None:
        return PredicateResult(
            passed=False,
            reason="seller_order_missing",
            diagnostics={"trip_id": trip_id},
        )
    hotel_id = str(order.get("hotel_id") or "").strip()
    if not hotel_id:
        return PredicateResult(
            passed=False,
            reason="hotel_id_empty",
            diagnostics={"trip_id": trip_id},
        )
    known = _find_inventory_hotel_ids(state)
    if known and hotel_id not in known:
        return PredicateResult(
            passed=False,
            reason="hotel_id_not_in_inventory",
            diagnostics={"trip_id": trip_id, "hotel_id": hotel_id,
                         "known_hotel_ids": sorted(known)},
        )
    return PredicateResult(
        passed=True,
        reason="hotel_id_present_ok",
        diagnostics={"trip_id": trip_id, "hotel_id": hotel_id},
    )


def booking_quantity_matches(
    state: EnvState,
    trip_id: str,
    expected_quantity: int,
) -> PredicateResult:
    """``seller_orders.quantity`` equals the seed-declared quantity. Catches
    cases where the model confirms with the wrong room count.
    """
    order = _find_seller_order(state, trip_id)
    if order is None:
        return PredicateResult(
            passed=False,
            reason="seller_order_missing",
            diagnostics={"trip_id": trip_id},
        )
    raw = order.get("quantity")
    try:
        quantity = int(raw) if raw is not None else None
    except (TypeError, ValueError):
        quantity = None
    if quantity is None:
        return PredicateResult(
            passed=False,
            reason="quantity_missing",
            diagnostics={"trip_id": trip_id, "raw_quantity": raw},
        )
    if quantity != int(expected_quantity):
        return PredicateResult(
            passed=False,
            reason="quantity_mismatch",
            diagnostics={"trip_id": trip_id, "quantity": quantity,
                         "expected_quantity": int(expected_quantity)},
        )
    return PredicateResult(
        passed=True,
        reason="booking_quantity_matches_ok",
        diagnostics={"trip_id": trip_id, "quantity": quantity},
    )


def approval_referenced(
    state: EnvState,
    trip_id: str,
) -> PredicateResult:
    """Cross-action correlation: the ``seller_orders`` row's
    ``approval_id`` must equal the ``approval_id`` of an approved
    ``approval_log`` row for the same trip_id.

    Catches the failure mode where the traveler passes
    ``delegate_authorization_code`` (or any other token) to
    ``confirm_booking`` instead of the approval_id returned by
    ``issue_approval``.
    """
    order = _find_seller_order(state, trip_id)
    if order is None:
        return PredicateResult(
            passed=False,
            reason="seller_order_missing",
            diagnostics={"trip_id": trip_id},
        )
    seller_approval_id = str(order.get("approval_id") or "").strip()
    if not seller_approval_id:
        return PredicateResult(
            passed=False,
            reason="seller_order_approval_id_missing",
            diagnostics={"trip_id": trip_id},
        )
    matches: list[Mapping[str, Any]] = []
    for row in state.db.get("approval_log", {}).values():
        if not isinstance(row, Mapping):
            continue
        if str(row.get("trip_id") or "") != trip_id:
            continue
        if str(row.get("status") or "").lower() != "approved":
            continue
        if str(row.get("approval_id") or "").strip() == seller_approval_id:
            matches.append(row)
    if not matches:
        approved_ids = sorted(
            str(r.get("approval_id") or "")
            for r in state.db.get("approval_log", {}).values()
            if isinstance(r, Mapping) and str(r.get("trip_id") or "") == trip_id
            and str(r.get("status") or "").lower() == "approved"
        )
        return PredicateResult(
            passed=False,
            reason="approval_id_not_in_approval_log",
            diagnostics={
                "trip_id": trip_id,
                "seller_approval_id": seller_approval_id,
                "approved_approval_ids_for_trip": approved_ids,
            },
        )
    return PredicateResult(
        passed=True,
        reason="approval_referenced_ok",
        diagnostics={"trip_id": trip_id, "approval_id": seller_approval_id},
    )


PREDICATE_REGISTRY: dict[str, Any] = {
    "travel.unit_rate_in_zone": unit_rate_in_zone,
    "travel.hotel_id_present": hotel_id_present,
    "travel.booking_quantity_matches": booking_quantity_matches,
    "travel.approval_referenced": approval_referenced,
}
