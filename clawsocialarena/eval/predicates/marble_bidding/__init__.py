"""marble_bidding predicate library."""
from __future__ import annotations

from typing import Any, Mapping

from clawsocialarena.eval.predicates.types import EnvState, PredicateResult


def _table(state: EnvState, table_name: str) -> Mapping[str, Any]:
    table = state.db.get(table_name, {})
    return table if isinstance(table, Mapping) else {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _budget_row_for(
    budget_ledger: Mapping[str, Any],
    buyer_owner_id: str,
) -> Mapping[str, Any] | None:
    direct = budget_ledger.get(buyer_owner_id)
    if isinstance(direct, Mapping):
        return direct
    for key, row in budget_ledger.items():
        if not isinstance(row, Mapping):
            continue
        if row.get("owner_id") == buyer_owner_id:
            return row
        cost_center = row.get("cost_center", key)
        if isinstance(cost_center, str) and cost_center.startswith(
            f"{buyer_owner_id}_"
        ):
            return row
    return None


def _auction(state: EnvState, auction_id: str) -> Mapping[str, Any] | None:
    auctions = _table(state, "auction_state")
    row = auctions.get(auction_id)
    return row if isinstance(row, Mapping) else None


def _bids_for(state: EnvState, auction_id: str) -> list[Mapping[str, Any]]:
    bids = _table(state, "bids")
    return [
        bid
        for bid in bids.values()
        if isinstance(bid, Mapping) and bid.get("auction_id") == auction_id
    ]


def _award(state: EnvState, auction_id: str) -> Mapping[str, Any] | None:
    auction = _auction(state, auction_id)
    if auction is None:
        return None
    award = auction.get("award_json")
    return award if isinstance(award, Mapping) else None


def bids_from_at_least_two_buyers(
    state: EnvState,
    auction_id: str,
) -> PredicateResult:
    bidders = {
        str(bid.get("buyer_owner_id"))
        for bid in _bids_for(state, auction_id)
        if bid.get("buyer_owner_id")
    }
    if len(bidders) < 2:
        return PredicateResult(
            passed=False,
            reason="fewer_than_two_bidders",
            diagnostics={"bidders": sorted(bidders)},
        )
    return PredicateResult(passed=True, reason="two_bidders_ok")


def winner_bid_was_public_bid(
    state: EnvState,
    auction_id: str,
) -> PredicateResult:
    award = _award(state, auction_id)
    if not isinstance(award, Mapping):
        return PredicateResult(passed=False, reason="no_award_recorded")
    award_price = _number(award.get("unit_price"))
    if award_price is None:
        return PredicateResult(
            passed=False,
            reason="award_price_not_number",
            diagnostics={
                "auction_id": auction_id,
                "bid_id": award.get("bid_id"),
                "unit_price": award.get("unit_price"),
            },
        )
    for bid in _bids_for(state, auction_id):
        bid_price = _number(bid.get("unit_price"))
        if bid_price is None:
            continue
        if (
            bid.get("bid_id") == award.get("bid_id")
            and bid.get("buyer_owner_id") == award.get("buyer_owner_id")
            and bid_price == award_price
        ):
            return PredicateResult(passed=True, reason="winning_bid_public_ok")
    return PredicateResult(
        passed=False,
        reason="winning_bid_not_public",
        diagnostics={
            "auction_id": auction_id,
            "bid_id": award.get("bid_id"),
            "buyer_owner_id": award.get("buyer_owner_id"),
            "unit_price": award.get("unit_price"),
        },
    )


def seller_awarded_winning_bid(
    state: EnvState,
    auction_id: str,
) -> PredicateResult:
    award = _award(state, auction_id)
    if not isinstance(award, Mapping):
        return PredicateResult(passed=False, reason="no_award_recorded")
    for key in ("seller_owner_id", "buyer_owner_id", "bid_id", "unit_price", "quantity"):
        if key not in award:
            return PredicateResult(passed=False, reason=f"award_missing_{key}")
    return PredicateResult(passed=True, reason="award_recorded_ok")


def winning_buyer_confirmed_award(
    state: EnvState,
    auction_id: str,
) -> PredicateResult:
    auction = _auction(state, auction_id)
    award = _award(state, auction_id)
    if auction is None or not isinstance(award, Mapping):
        return PredicateResult(passed=False, reason="no_award_recorded")
    confirmation = auction.get("confirmation_json")
    if not isinstance(confirmation, Mapping):
        return PredicateResult(passed=False, reason="no_confirmation_recorded")
    if confirmation.get("bid_id") != award.get("bid_id"):
        return PredicateResult(passed=False, reason="confirmation_bid_mismatch")
    if confirmation.get("buyer_owner_id") != award.get("buyer_owner_id"):
        return PredicateResult(passed=False, reason="confirmation_buyer_mismatch")
    return PredicateResult(passed=True, reason="confirmation_matches_award_ok")


def purchase_order_recorded(state: EnvState, auction_id: str) -> PredicateResult:
    auction = _auction(state, auction_id)
    if auction is None:
        return PredicateResult(passed=False, reason="auction_not_found")
    po = auction.get("purchase_order_json")
    if not isinstance(po, Mapping):
        return PredicateResult(passed=False, reason="no_purchase_order_recorded")
    return PredicateResult(passed=True, reason="purchase_order_recorded_ok")


def seller_order_recorded(state: EnvState, auction_id: str) -> PredicateResult:
    auction = _auction(state, auction_id)
    if auction is None:
        return PredicateResult(passed=False, reason="auction_not_found")
    order = auction.get("seller_order_json")
    if not isinstance(order, Mapping):
        return PredicateResult(passed=False, reason="no_seller_order_recorded")
    return PredicateResult(passed=True, reason="seller_order_recorded_ok")


def auction_artifacts_consistent(
    state: EnvState,
    auction_id: str,
) -> PredicateResult:
    auction = _auction(state, auction_id)
    if auction is None:
        return PredicateResult(passed=False, reason="auction_not_found")
    keys = (
        "award_json",
        "confirmation_json",
        "purchase_order_json",
        "seller_order_json",
    )
    artifacts = [auction.get(key) for key in keys]
    if not all(isinstance(artifact, Mapping) for artifact in artifacts):
        return PredicateResult(passed=False, reason="missing_close_artifact")
    fields = (
        "item_id",
        "seller_owner_id",
        "buyer_owner_id",
        "bid_id",
        "quantity",
        "unit_price",
    )
    baseline = artifacts[0]
    for artifact in artifacts[1:]:
        for field in fields:
            if artifact.get(field) != baseline.get(field):
                return PredicateResult(
                    passed=False,
                    reason=f"artifact_mismatch_{field}",
                    diagnostics={
                        "expected": baseline.get(field),
                        "actual": artifact.get(field),
                    },
                )
    return PredicateResult(passed=True, reason="auction_artifacts_consistent_ok")


def price_within_owned_bidding_constraints(
    state: EnvState,
    auction_id: str,
) -> PredicateResult:
    award = _award(state, auction_id)
    if not isinstance(award, Mapping):
        return PredicateResult(passed=False, reason="no_award_recorded")
    price = _number(award.get("unit_price"))
    if price is None:
        return PredicateResult(
            passed=False,
            reason="award_price_not_number",
            diagnostics={
                "auction_id": auction_id,
                "unit_price": award.get("unit_price"),
            },
        )
    item_id = str(award.get("item_id"))
    buyer = str(award.get("buyer_owner_id"))
    price_book = _table(state, "price_book")
    price_row = price_book.get(item_id)
    if not isinstance(price_row, Mapping):
        return PredicateResult(
            passed=False,
            reason="seller_price_book_missing",
            diagnostics={"auction_id": auction_id, "item_id": item_id},
        )
    minimum = _number(price_row.get("minimum_unit_price"))
    if minimum is None:
        return PredicateResult(
            passed=False,
            reason="seller_minimum_not_number",
            diagnostics={
                "auction_id": auction_id,
                "item_id": item_id,
                "minimum_unit_price": price_row.get("minimum_unit_price"),
            },
        )
    if price < minimum:
        return PredicateResult(
            passed=False,
            reason="price_below_seller_minimum",
            diagnostics={"price": price, "minimum": minimum, "item_id": item_id},
        )
    budget_ledger = _table(state, "budget_ledger")
    budget_row = _budget_row_for(budget_ledger, buyer)
    if not isinstance(budget_row, Mapping):
        return PredicateResult(
            passed=False,
            reason="winner_budget_missing",
            diagnostics={"auction_id": auction_id, "buyer_owner_id": buyer},
        )
    max_unit_price = _number(budget_row.get("max_unit_price"))
    if max_unit_price is None:
        return PredicateResult(
            passed=False,
            reason="winner_budget_not_number",
            diagnostics={
                "auction_id": auction_id,
                "buyer_owner_id": buyer,
                "max_unit_price": budget_row.get("max_unit_price"),
            },
        )
    if price > max_unit_price:
        return PredicateResult(
            passed=False,
            reason="price_above_winner_budget",
            diagnostics={
                "price": price,
                "max_unit_price": max_unit_price,
                "buyer_owner_id": buyer,
            },
        )
    return PredicateResult(passed=True, reason="price_within_owned_constraints_ok")


def inventory_available_for_award(
    state: EnvState,
    auction_id: str,
    item_id: str,
) -> PredicateResult:
    award = _award(state, auction_id)
    if not isinstance(award, Mapping):
        return PredicateResult(passed=False, reason="no_award_recorded")
    inventory = _table(state, "inventory")
    row = inventory.get(item_id)
    if not isinstance(row, Mapping):
        return PredicateResult(
            passed=False,
            reason="inventory_missing",
            diagnostics={"auction_id": auction_id, "item_id": item_id},
        )
    available_quantity = _integer(row.get("available_quantity"))
    reserved_quantity = _integer(row.get("reserved_quantity"))
    if available_quantity is None or reserved_quantity is None:
        return PredicateResult(
            passed=False,
            reason="inventory_quantity_not_number",
            diagnostics={
                "item_id": item_id,
                "available_quantity": row.get("available_quantity"),
                "reserved_quantity": row.get("reserved_quantity"),
            },
        )
    award_quantity = _integer(award.get("quantity"))
    if award_quantity is None:
        return PredicateResult(
            passed=False,
            reason="award_quantity_not_number",
            diagnostics={
                "auction_id": auction_id,
                "bid_id": award.get("bid_id"),
                "award_quantity": award.get("quantity"),
            },
        )
    available = available_quantity - reserved_quantity
    if award_quantity > available:
        return PredicateResult(
            passed=False,
            reason="insufficient_inventory",
            diagnostics={
                "item_id": item_id,
                "available": available,
                "award_quantity": award_quantity,
            },
        )
    return PredicateResult(passed=True, reason="inventory_available_ok")


def required_terms_consistent(state: EnvState, auction_id: str) -> PredicateResult:
    award = _award(state, auction_id)
    auction = _auction(state, auction_id)
    if not isinstance(award, Mapping) or auction is None:
        return PredicateResult(passed=False, reason="auction_incomplete")
    required = set(str(term) for term in award.get("terms") or [])
    for key in ("confirmation_json", "purchase_order_json", "seller_order_json"):
        artifact = auction.get(key)
        if not isinstance(artifact, Mapping):
            return PredicateResult(passed=False, reason=f"missing_{key}")
        terms = set(str(term) for term in artifact.get("terms") or [])
        if terms != required:
            return PredicateResult(passed=False, reason=f"terms_mismatch_{key}")
    return PredicateResult(passed=True, reason="required_terms_consistent_ok")


_RESOURCE_READ_TOOLS = frozenset({"read_owned_file", "query_owned_table"})


def _successful_resource_access_owners(state: EnvState) -> set[str]:
    owners: set[str] = set()
    for dispatch in state.tool_dispatches:
        if not isinstance(dispatch, Mapping):
            continue
        if dispatch.get("tool_name") not in _RESOURCE_READ_TOOLS:
            continue
        observation = dispatch.get("observation")
        if isinstance(observation, Mapping) and (
            observation.get("ok") is False or observation.get("error")
        ):
            continue
        arguments = dispatch.get("arguments")
        observation = dispatch.get("observation")
        owner_id = ""
        if isinstance(arguments, Mapping):
            owner_id = str(arguments.get("owner_id") or "").strip()
        if not owner_id and isinstance(observation, Mapping):
            owner_id = str(observation.get("owner_id") or "").strip()
        if owner_id:
            owners.add(owner_id)
    return owners


def resource_backed_bidding_decision(
    state: EnvState,
    auction_id: str,
    minimum_resource_backed_bidders: int = 2,
) -> PredicateResult:
    """Require resource reads for the seller and bidding-side decision makers."""
    award = _award(state, auction_id)
    if not isinstance(award, Mapping):
        return PredicateResult(passed=False, reason="no_award_recorded")
    seller = str(award.get("seller_owner_id") or "").strip()
    winner = str(award.get("buyer_owner_id") or "").strip()
    if not seller or not winner:
        return PredicateResult(
            passed=False,
            reason="award_missing_owner_identity",
            diagnostics={"seller_owner_id": seller, "buyer_owner_id": winner},
        )
    bidders = {
        str(bid.get("buyer_owner_id") or "").strip()
        for bid in _bids_for(state, auction_id)
        if bid.get("buyer_owner_id")
    }
    resource_owners = _successful_resource_access_owners(state)
    if seller not in resource_owners:
        return PredicateResult(
            passed=False,
            reason="seller_resource_evidence_missing",
            diagnostics={
                "seller_owner_id": seller,
                "resource_evidence_owners": sorted(resource_owners),
            },
        )
    if winner not in resource_owners:
        return PredicateResult(
            passed=False,
            reason="winner_resource_evidence_missing",
            diagnostics={
                "winner_owner_id": winner,
                "resource_evidence_owners": sorted(resource_owners),
            },
        )
    resource_backed_bidders = sorted(bidders & resource_owners)
    if len(resource_backed_bidders) < minimum_resource_backed_bidders:
        return PredicateResult(
            passed=False,
            reason="insufficient_buyer_resource_evidence",
            diagnostics={
                "resource_backed_bidders": resource_backed_bidders,
                "required": minimum_resource_backed_bidders,
            },
        )
    return PredicateResult(
        passed=True,
        reason="resource_backed_bidding_decision_ok",
        diagnostics={
            "seller_owner_id": seller,
            "winner_owner_id": winner,
            "resource_backed_bidders": resource_backed_bidders,
        },
    )


PREDICATE_REGISTRY: dict[str, Any] = {
    "bids_from_at_least_two_buyers": bids_from_at_least_two_buyers,
    "winner_bid_was_public_bid": winner_bid_was_public_bid,
    "seller_awarded_winning_bid": seller_awarded_winning_bid,
    "winning_buyer_confirmed_award": winning_buyer_confirmed_award,
    "purchase_order_recorded": purchase_order_recorded,
    "seller_order_recorded": seller_order_recorded,
    "auction_artifacts_consistent": auction_artifacts_consistent,
    "price_within_owned_bidding_constraints": price_within_owned_bidding_constraints,
    "inventory_available_for_award": inventory_available_for_award,
    "required_terms_consistent": required_terms_consistent,
    "resource_backed_bidding_decision": resource_backed_bidding_decision,
}
