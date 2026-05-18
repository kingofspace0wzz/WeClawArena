"""Owned-ecosystem marble_bargaining predicate library."""
from __future__ import annotations

import json
from typing import Any, Mapping

from clawsocialarena.eval.predicates.types import EnvState, PredicateResult


def purchase_order_recorded(
    state: EnvState,
    transaction_id: str,
) -> PredicateResult:
    purchase_order = _purchase_order(state, transaction_id)
    if purchase_order is None:
        return PredicateResult(passed=False, reason="purchase_order_missing")
    if purchase_order.get("transaction_id") != transaction_id:
        return PredicateResult(passed=False, reason="purchase_order_transaction_mismatch")
    if not purchase_order.get("po_id"):
        return PredicateResult(passed=False, reason="purchase_order_missing_po_id")
    return PredicateResult(passed=True, reason="purchase_order_recorded_ok")


def seller_order_recorded(
    state: EnvState,
    transaction_id: str,
) -> PredicateResult:
    seller_acceptance = _seller_acceptance(state, transaction_id)
    if seller_acceptance is None:
        return PredicateResult(passed=False, reason="seller_order_missing")
    if seller_acceptance.get("transaction_id") != transaction_id:
        return PredicateResult(passed=False, reason="seller_order_transaction_mismatch")
    if not seller_acceptance.get("order_id"):
        return PredicateResult(passed=False, reason="seller_order_missing_order_id")
    return PredicateResult(passed=True, reason="seller_order_recorded_ok")


def approval_log_recorded(
    state: EnvState,
    transaction_id: str,
) -> PredicateResult:
    approval = _approval(state, transaction_id)
    if approval is None:
        return PredicateResult(passed=False, reason="approval_log_missing")
    if approval.get("transaction_id") != transaction_id:
        return PredicateResult(passed=False, reason="approval_transaction_mismatch")
    if not approval.get("approval_id"):
        return PredicateResult(passed=False, reason="approval_missing_approval_id")
    return PredicateResult(passed=True, reason="approval_log_recorded_ok")


def transaction_artifacts_consistent(
    state: EnvState,
    transaction_id: str,
    item_id: str | None = None,
) -> PredicateResult:
    purchase_order = _purchase_order(state, transaction_id)
    seller_acceptance = _seller_acceptance(state, transaction_id)
    approval = _approval(state, transaction_id)
    if purchase_order is None:
        return PredicateResult(passed=False, reason="purchase_order_missing")
    if seller_acceptance is None:
        return PredicateResult(passed=False, reason="seller_order_missing")
    if approval is None:
        return PredicateResult(passed=False, reason="approval_log_missing")

    field_groups = {
        "transaction_id": (
            purchase_order.get("transaction_id"),
            seller_acceptance.get("transaction_id"),
            approval.get("transaction_id"),
        ),
        "item_id": (
            purchase_order.get("item_id"),
            seller_acceptance.get("item_id"),
            approval.get("item_id"),
        ),
        "quantity": (
            purchase_order.get("quantity"),
            seller_acceptance.get("quantity"),
            approval.get("quantity"),
        ),
        "unit_price": (
            purchase_order.get("unit_price"),
            seller_acceptance.get("unit_price"),
            approval.get("unit_price"),
        ),
        "warranty_months": (
            purchase_order.get("warranty_months"),
            seller_acceptance.get("warranty_months"),
            approval.get("warranty_months"),
        ),
        "approval_id": (
            purchase_order.get("approval_id"),
            seller_acceptance.get("approval_id"),
            approval.get("approval_id"),
        ),
    }
    for field, values in field_groups.items():
        if len(set(values)) != 1:
            return PredicateResult(
                passed=False,
                reason=f"{field}_mismatch",
                diagnostics={"field": field, "values": list(values)},
            )
    return PredicateResult(passed=True, reason="transaction_artifacts_consistent_ok")


def price_within_owned_constraints(
    state: EnvState,
    transaction_id: str,
) -> PredicateResult:
    purchase_order = _purchase_order(state, transaction_id)
    if purchase_order is None:
        return PredicateResult(passed=False, reason="purchase_order_missing")
    item_id = str(purchase_order.get("item_id") or "")
    quantity = _number(purchase_order.get("quantity"))
    unit_price = _number(purchase_order.get("unit_price"))
    warranty_months = int(purchase_order.get("warranty_months") or 0)
    if not item_id or quantity is None or unit_price is None:
        return PredicateResult(passed=False, reason="purchase_order_terms_incomplete")

    budget = _first_row(state.db.get("budget_ledger", {}))
    if budget is None or _number(budget.get("remaining_budget")) is None:
        return PredicateResult(passed=False, reason="budget_ledger_missing")
    remaining_budget = float(budget["remaining_budget"])
    total_price = float(quantity) * float(unit_price)
    if total_price > remaining_budget:
        return PredicateResult(
            passed=False,
            reason="total_price_exceeds_budget",
            diagnostics={"total_price": total_price, "remaining_budget": remaining_budget},
        )

    price_book = state.db.get("price_book", {}).get(item_id)
    if not isinstance(price_book, Mapping):
        return PredicateResult(passed=False, reason="price_book_missing")
    minimum = _number(price_book.get("minimum_unit_price"))
    if minimum is None:
        return PredicateResult(passed=False, reason="minimum_unit_price_missing")
    if float(unit_price) < minimum:
        return PredicateResult(
            passed=False,
            reason="unit_price_below_minimum",
            diagnostics={"unit_price": unit_price, "minimum_unit_price": minimum},
        )
    warranty_minimum = _number(price_book.get("warranty_24_month_min_price"))
    if warranty_months == 24 and warranty_minimum is not None:
        if float(unit_price) < warranty_minimum:
            return PredicateResult(
                passed=False,
                reason="unit_price_below_warranty_minimum",
                diagnostics={
                    "unit_price": unit_price,
                    "warranty_24_month_min_price": warranty_minimum,
                },
            )
    return PredicateResult(passed=True, reason="price_within_owned_constraints_ok")


def inventory_allocation_feasible(
    state: EnvState,
    transaction_id: str,
) -> PredicateResult:
    purchase_order = _purchase_order(state, transaction_id)
    if purchase_order is None:
        return PredicateResult(passed=False, reason="purchase_order_missing")

    item_id = str(purchase_order.get("item_id") or "")
    purchase_quantity = _number(purchase_order.get("quantity"))
    if not item_id or purchase_quantity is None:
        return PredicateResult(passed=False, reason="purchase_order_terms_incomplete")

    inventory = state.db.get("inventory", {}).get(item_id)
    if not isinstance(inventory, Mapping):
        return PredicateResult(
            passed=False,
            reason="inventory_missing",
            diagnostics={"item_id": item_id},
        )
    available_quantity = _number(inventory.get("available_quantity"))
    reserved_quantity = _number(inventory.get("reserved_quantity"))
    if available_quantity is None or reserved_quantity is None:
        return PredicateResult(
            passed=False,
            reason="inventory_quantities_incomplete",
            diagnostics={"item_id": item_id},
        )

    movable_quantity = 0.0
    for allocation in state.db.get("inventory_allocations", {}).values():
        if not isinstance(allocation, Mapping):
            continue
        if allocation.get("item_id") != item_id or not allocation.get("movable"):
            continue
        quantity = _number(allocation.get("quantity"))
        if quantity is not None:
            movable_quantity += quantity

    free_quantity = available_quantity - reserved_quantity
    feasible_quantity = free_quantity + movable_quantity
    diagnostics = {
        "item_id": item_id,
        "purchase_quantity": purchase_quantity,
        "available_quantity": available_quantity,
        "reserved_quantity": reserved_quantity,
        "free_quantity": free_quantity,
        "movable_quantity": movable_quantity,
        "feasible_quantity": feasible_quantity,
    }
    if feasible_quantity < purchase_quantity:
        return PredicateResult(
            passed=False,
            reason="inventory_allocation_insufficient",
            diagnostics=diagnostics,
        )
    return PredicateResult(
        passed=True,
        reason="inventory_allocation_feasible_ok",
        diagnostics=diagnostics,
    )


def shipping_terms_consistent(
    state: EnvState,
    transaction_id: str,
) -> PredicateResult:
    return _required_terms_consistent(
        state,
        transaction_id,
        ("delivery_date", "shipping_method", "temperature_range"),
        ok_reason="shipping_terms_consistent_ok",
    )


def prior_contract_terms_consistent(
    state: EnvState,
    transaction_id: str,
) -> PredicateResult:
    return _required_terms_consistent(
        state,
        transaction_id,
        ("prior_contract_id", "support_tier", "coterm_end_date"),
        ok_reason="prior_contract_terms_consistent_ok",
    )


def required_terms_consistent(
    state: EnvState,
    transaction_id: str,
    required_keys: tuple[str, ...] | list[str],
) -> PredicateResult:
    return _required_terms_consistent(
        state,
        transaction_id,
        tuple(str(key) for key in required_keys),
        ok_reason="required_terms_consistent_ok",
    )


def _purchase_order(
    state: EnvState,
    transaction_id: str,
) -> Mapping[str, Any] | None:
    state_record = _state_record(state, transaction_id)
    if state_record is not None:
        purchase_order = state_record.get("purchase_order")
        if isinstance(purchase_order, Mapping):
            return purchase_order
    for row in state.db.get("purchase_orders", {}).values():
        if isinstance(row, Mapping) and row.get("transaction_id") == transaction_id:
            return row
    return None


def _seller_acceptance(
    state: EnvState,
    transaction_id: str,
) -> Mapping[str, Any] | None:
    state_record = _state_record(state, transaction_id)
    if state_record is not None:
        seller_acceptance = state_record.get("seller_acceptance")
        if isinstance(seller_acceptance, Mapping):
            return seller_acceptance
    for row in state.db.get("seller_orders", {}).values():
        if isinstance(row, Mapping) and row.get("transaction_id") == transaction_id:
            return row
    return None


def _approval(
    state: EnvState,
    transaction_id: str,
) -> Mapping[str, Any] | None:
    purchase_order = _purchase_order(state, transaction_id)
    approval_id = purchase_order.get("approval_id") if purchase_order else None
    approval_log = state.db.get("approval_log", {})
    if approval_id and isinstance(approval_log.get(str(approval_id)), Mapping):
        return approval_log[str(approval_id)]
    for row in approval_log.values():
        if isinstance(row, Mapping) and row.get("transaction_id") == transaction_id:
            return row
    return None


def _state_record(
    state: EnvState,
    transaction_id: str,
) -> Mapping[str, Any] | None:
    row = state.db.get("negotiation_state", {}).get(transaction_id)
    return row if isinstance(row, Mapping) else None


def _first_row(rows: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for row in rows.values():
        if isinstance(row, Mapping):
            return row
    return None


def _required_terms_consistent(
    state: EnvState,
    transaction_id: str,
    required_keys: tuple[str, ...],
    *,
    ok_reason: str = "required_terms_consistent_ok",
) -> PredicateResult:
    purchase_order = _purchase_order(state, transaction_id)
    seller_acceptance = _seller_acceptance(state, transaction_id)
    approval = _approval(state, transaction_id)
    if purchase_order is None:
        return PredicateResult(passed=False, reason="purchase_order_missing")
    if seller_acceptance is None:
        return PredicateResult(passed=False, reason="seller_order_missing")
    if approval is None:
        return PredicateResult(passed=False, reason="approval_log_missing")

    records = {
        "purchase_order": purchase_order,
        "seller_acceptance": seller_acceptance,
        "approval": approval,
    }
    terms_by_record = {name: _terms(record) for name, record in records.items()}
    for key in required_keys:
        missing_from = [
            name
            for name, terms in terms_by_record.items()
            if key not in terms or terms[key] is None or terms[key] == ""
        ]
        if missing_from:
            return PredicateResult(
                passed=False,
                reason=f"{key}_missing",
                diagnostics={
                    "key": key,
                    "missing_from": missing_from,
                },
            )
        values = {name: terms[key] for name, terms in terms_by_record.items()}
        purchase_value = values["purchase_order"]
        if any(value != purchase_value for value in values.values()):
            return PredicateResult(
                passed=False,
                reason=f"{key}_mismatch",
                diagnostics={"key": key, "values": values},
            )
    return PredicateResult(
        passed=True,
        reason=ok_reason,
        diagnostics={"required_keys": list(required_keys)},
    )


def _terms(record: Mapping[str, Any]) -> Mapping[str, Any]:
    terms = record.get("terms")
    if isinstance(terms, Mapping):
        return terms
    terms_json = record.get("terms_json")
    if isinstance(terms_json, Mapping):
        return terms_json
    if not isinstance(terms_json, str) or not terms_json.strip():
        return {}
    try:
        decoded = json.loads(terms_json)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, Mapping) else {}


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


PREDICATE_REGISTRY: dict[str, Any] = {
    "purchase_order_recorded": purchase_order_recorded,
    "seller_order_recorded": seller_order_recorded,
    "approval_log_recorded": approval_log_recorded,
    "transaction_artifacts_consistent": transaction_artifacts_consistent,
    "price_within_owned_constraints": price_within_owned_constraints,
    "inventory_allocation_feasible": inventory_allocation_feasible,
    "shipping_terms_consistent": shipping_terms_consistent,
    "prior_contract_terms_consistent": prior_contract_terms_consistent,
    "required_terms_consistent": required_terms_consistent,
}
