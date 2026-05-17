"""Tests for tau2_retail evaluation predicates."""
from __future__ import annotations

from clawsocialarena.eval.predicates.tau2_retail import (
    aggregated_order_includes_all_spokes,
    cross_account_gift_consent_recorded,
    customer_authenticated_via,
    household_order_finalized_for,
    household_payment_authorized_by,
    refund_routed_to_original_payment_method,
    shared_account_order_finalized_for,
    shared_account_payment_authorized_by,
    shipping_address_is_household_owned,
    shipping_address_is_shared_account_owned,
    spoke_request_not_read_cross_spoke,
    transfer_to_human_called_for_out_of_scope,
    user_confirmation_recorded_before,
)
from clawsocialarena.eval.predicates.types import EnvState


def _make_state(**db_overrides) -> EnvState:
    """Build an EnvState with the given db keys; other attributes are empty."""
    return EnvState(db=db_overrides, outbound_messages=[], tool_dispatches=[], metadata={})


# ---------------------------------------------------------------------------
# Back-compat shim tests (3 tests)
# ---------------------------------------------------------------------------


def test_household_order_finalized_for_accepts_household_id_kwarg() -> None:
    """household_order_finalized_for passes household_id kwarg through to the
    shared_account canonical implementation."""
    state = _make_state(orders={"#W-1": {"household_id": "HH-7", "status": "finalized"}})
    result = household_order_finalized_for(state, order_id="#W-1", household_id="HH-7")
    assert result.passed
    assert result.reason == "terminal_ok"


def test_household_payment_authorized_by_back_compat() -> None:
    """household_payment_authorized_by delegates correctly."""
    state = _make_state(
        orders={"#W-2": {"payment_authorized_by": "alice"}}
    )
    result = household_payment_authorized_by(
        state, order_id="#W-2", expected_authorizer_id="alice"
    )
    assert result.passed
    assert result.reason == "authorized_ok"


def test_shipping_address_is_household_owned_back_compat() -> None:
    """shipping_address_is_household_owned delegates household_id -> shared_account_id."""
    state = _make_state(
        orders={
            "#W-3": {
                "shipping_address": {"household_id": "HH-9", "street": "1 Main St"}
            }
        }
    )
    result = shipping_address_is_household_owned(
        state, order_id="#W-3", household_id="HH-9"
    )
    assert result.passed
    assert result.reason == "address_ok"


# ---------------------------------------------------------------------------
# shared_account_order_finalized_for (positive + negative + back-compat row)
# ---------------------------------------------------------------------------


def test_shared_account_order_finalized_for_passes_on_finalized_order() -> None:
    state = _make_state(orders={"#W-1": {"shared_account_id": "HH-7", "status": "finalized"}})
    result = shared_account_order_finalized_for(state, order_id="#W-1", shared_account_id="HH-7")
    assert result.passed
    assert result.reason == "terminal_ok"


def test_shared_account_order_finalized_for_back_compat_household_id_in_row() -> None:
    """Row uses old household_id key; predicate should still pass."""
    state = _make_state(orders={"#W-1": {"household_id": "HH-7", "status": "finalized"}})
    result = shared_account_order_finalized_for(state, order_id="#W-1", shared_account_id="HH-7")
    assert result.passed


def test_shared_account_order_finalized_for_fails_on_wrong_account() -> None:
    state = _make_state(orders={"#W-1": {"shared_account_id": "HH-8", "status": "finalized"}})
    result = shared_account_order_finalized_for(state, order_id="#W-1", shared_account_id="HH-7")
    assert not result.passed
    assert result.reason == "shared_account_mismatch"
    assert result.diagnostics["expected"] == "HH-7"
    assert result.diagnostics["actual"] == "HH-8"


def test_shared_account_order_finalized_for_fails_on_non_terminal_status() -> None:
    state = _make_state(orders={"#W-1": {"shared_account_id": "HH-7", "status": "pending"}})
    result = shared_account_order_finalized_for(state, order_id="#W-1", shared_account_id="HH-7")
    assert not result.passed
    assert "pending" in result.reason


def test_shared_account_order_finalized_for_accepts_exchange_requested() -> None:
    state = _make_state(
        orders={"#W-1": {"shared_account_id": "HH-7", "status": "exchange_requested"}}
    )
    result = shared_account_order_finalized_for(state, order_id="#W-1", shared_account_id="HH-7")
    assert result.passed


# ---------------------------------------------------------------------------
# cross_account_gift_consent_recorded (positive + negative)
# ---------------------------------------------------------------------------


def test_cross_account_gift_consent_recorded_passes_when_granted() -> None:
    state = _make_state(
        **{
            "incoming_gift_requests::diego": {
                "#W-GIFT-1": {
                    "consent_status": "granted",
                    "granted_at": "2026-05-10T10:00:00Z",
                }
            },
            "orders": {
                "#W-GIFT-1": {"committed_at": "2026-05-10T11:00:00Z"}
            },
        }
    )
    result = cross_account_gift_consent_recorded(
        state, order_id="#W-GIFT-1", recipient_owner_id="diego"
    )
    assert result.passed
    assert result.reason == "consent_recorded_before_commit"


def test_cross_account_gift_consent_recorded_requires_granted() -> None:
    state = _make_state(
        **{
            "incoming_gift_requests::diego": {
                "#W-GIFT-1": {"consent_status": "pending", "granted_at": None}
            }
        }
    )
    result = cross_account_gift_consent_recorded(
        state, order_id="#W-GIFT-1", recipient_owner_id="diego"
    )
    assert not result.passed
    assert "consent_status_not_granted" in result.reason


def test_cross_account_gift_consent_recorded_fails_when_row_missing() -> None:
    state = _make_state(**{"incoming_gift_requests::diego": {}})
    result = cross_account_gift_consent_recorded(
        state, order_id="#W-GIFT-1", recipient_owner_id="diego"
    )
    assert not result.passed
    assert result.reason == "consent_row_missing"


def test_cross_account_gift_consent_recorded_fails_when_consent_after_commit() -> None:
    state = _make_state(
        **{
            "incoming_gift_requests::diego": {
                "#W-GIFT-2": {
                    "consent_status": "granted",
                    "granted_at": "2026-05-10T12:00:00Z",
                }
            },
            "orders": {
                "#W-GIFT-2": {"committed_at": "2026-05-10T11:00:00Z"}
            },
        }
    )
    result = cross_account_gift_consent_recorded(
        state, order_id="#W-GIFT-2", recipient_owner_id="diego"
    )
    assert not result.passed
    assert result.reason == "consent_after_commit"


# ---------------------------------------------------------------------------
# refund_routed_to_original_payment_method (positive + negative)
# ---------------------------------------------------------------------------


def test_refund_routed_to_original_payment_method_passes() -> None:
    state = _make_state(
        orders={
            "#W-R1": {
                "payment_history": [
                    {"type": "charge", "payment_method_id": "pm-42"},
                    {"type": "refund", "payment_method_id": "pm-42"},
                ]
            }
        }
    )
    result = refund_routed_to_original_payment_method(
        state, order_id="#W-R1", original_payment_method_id="pm-42"
    )
    assert result.passed
    assert result.reason == "refund_routed_ok"


def test_refund_routed_to_original_payment_method_fails_when_misrouted() -> None:
    state = _make_state(
        orders={
            "#W-R2": {
                "payment_history": [
                    {"type": "charge", "payment_method_id": "pm-42"},
                    {"type": "refund", "payment_method_id": "pm-99"},
                ]
            }
        }
    )
    result = refund_routed_to_original_payment_method(
        state, order_id="#W-R2", original_payment_method_id="pm-42"
    )
    assert not result.passed
    assert result.reason == "refund_misrouted"
    assert result.diagnostics["expected"] == "pm-42"
    assert result.diagnostics["actual"] == "pm-99"


def test_refund_routed_to_original_payment_method_fails_when_no_refund() -> None:
    state = _make_state(
        orders={"#W-R3": {"payment_history": [{"type": "charge", "payment_method_id": "pm-1"}]}}
    )
    result = refund_routed_to_original_payment_method(
        state, order_id="#W-R3", original_payment_method_id="pm-1"
    )
    assert not result.passed
    assert result.reason == "no_refund_in_history"


# ---------------------------------------------------------------------------
# customer_authenticated_via (positive + negative)
# ---------------------------------------------------------------------------


def test_customer_authenticated_via_passes() -> None:
    state = _make_state(
        auth_attempts={
            "att-1": {
                "customer_id_claimed": "cust-100",
                "verified": True,
                "method": "otp",
            }
        }
    )
    result = customer_authenticated_via(
        state, customer_id="cust-100", methods=("otp", "biometric")
    )
    assert result.passed
    assert result.reason == "authenticated_ok"


def test_customer_authenticated_via_fails_when_no_verified_attempt() -> None:
    state = _make_state(
        auth_attempts={
            "att-1": {
                "customer_id_claimed": "cust-100",
                "verified": False,
                "method": "otp",
            }
        }
    )
    result = customer_authenticated_via(
        state, customer_id="cust-100", methods=("otp", "biometric")
    )
    assert not result.passed
    assert result.reason == "no_verified_auth_attempt"


def test_customer_authenticated_via_fails_when_method_not_allowed() -> None:
    state = _make_state(
        auth_attempts={
            "att-1": {
                "customer_id_claimed": "cust-100",
                "verified": True,
                "method": "password",
            }
        }
    )
    result = customer_authenticated_via(
        state, customer_id="cust-100", methods=("otp", "biometric")
    )
    assert not result.passed


# ---------------------------------------------------------------------------
# user_confirmation_recorded_before (positive + negative)
# ---------------------------------------------------------------------------


def test_user_confirmation_recorded_before_passes() -> None:
    state = EnvState(
        db={"orders": {"#W-C1": {"exchange_committed_at": "2026-05-10T12:00:00Z"}}},
        outbound_messages=[
            {"ts": "2026-05-10T11:50:00Z", "content": "Yes, go ahead with the exchange."},
        ],
        tool_dispatches=[],
        metadata={},
    )
    result = user_confirmation_recorded_before(state, order_id="#W-C1", action="exchange")
    assert result.passed
    assert result.reason == "confirmation_found"


def test_user_confirmation_recorded_before_fails_when_no_confirmation() -> None:
    state = EnvState(
        db={"orders": {"#W-C2": {"exchange_committed_at": "2026-05-10T12:00:00Z"}}},
        outbound_messages=[
            {"ts": "2026-05-10T11:50:00Z", "content": "Please wait while I process."},
        ],
        tool_dispatches=[],
        metadata={},
    )
    result = user_confirmation_recorded_before(state, order_id="#W-C2", action="exchange")
    assert not result.passed
    assert result.reason == "no_confirmation_before_commit"


def test_user_confirmation_recorded_before_fails_when_confirmation_after_commit() -> None:
    state = EnvState(
        db={"orders": {"#W-C3": {"exchange_committed_at": "2026-05-10T12:00:00Z"}}},
        outbound_messages=[
            {"ts": "2026-05-10T12:05:00Z", "content": "Yes, confirmed."},
        ],
        tool_dispatches=[],
        metadata={},
    )
    result = user_confirmation_recorded_before(state, order_id="#W-C3", action="exchange")
    assert not result.passed
    assert result.reason == "no_confirmation_before_commit"


# ---------------------------------------------------------------------------
# aggregated_order_includes_all_spokes (positive + negative)
# ---------------------------------------------------------------------------


def test_aggregated_order_includes_all_spokes_passes() -> None:
    state = _make_state(
        order_line_items={
            "#W-AGG-1": [
                {"item_id": "I1", "originating_spoke_id": "sara"},
                {"item_id": "I2", "originating_spoke_id": "theo"},
                {"item_id": "I3", "originating_spoke_id": "uma"},
            ]
        }
    )
    result = aggregated_order_includes_all_spokes(
        state, order_id="#W-AGG-1", spoke_owner_ids=("sara", "theo", "uma")
    )
    assert result.passed
    assert result.reason == "all_spokes_present"


def test_aggregated_order_includes_all_spokes_lists_missing() -> None:
    state = _make_state(
        order_line_items={
            "#W-AGG-1": [
                {"item_id": "I1", "originating_spoke_id": "sara"},
                {"item_id": "I2", "originating_spoke_id": "theo"},
            ]
        }
    )
    result = aggregated_order_includes_all_spokes(
        state, order_id="#W-AGG-1", spoke_owner_ids=("sara", "theo", "uma")
    )
    assert not result.passed
    assert result.diagnostics["missing_spokes"] == ["uma"]


# ---------------------------------------------------------------------------
# spoke_request_not_read_cross_spoke (positive + negative)
# ---------------------------------------------------------------------------


def test_spoke_request_not_read_cross_spoke_passes_on_no_leak() -> None:
    state = EnvState(
        db={},
        outbound_messages=[],
        tool_dispatches=[
            {
                "caller_owner_id": "harriet",
                "resource_path": "agents/sara/files/my_purchase_request.md",
            },
        ],
        metadata={"hub_owner_id": "harriet"},
    )
    result = spoke_request_not_read_cross_spoke(
        state, spoke_id="sara", accessor_owner_ids=("sara", "theo", "uma", "harriet")
    )
    assert result.passed
    assert result.reason == "cross_spoke_isolation_ok"


def test_spoke_request_not_read_cross_spoke_flags_cross_spoke_read() -> None:
    state = EnvState(
        db={},
        outbound_messages=[],
        tool_dispatches=[
            {
                "caller_owner_id": "theo",
                "resource_path": "agents/sara/files/my_preferences.md",
            },
        ],
        metadata={"hub_owner_id": "harriet"},
    )
    result = spoke_request_not_read_cross_spoke(
        state, spoke_id="sara", accessor_owner_ids=("sara", "theo", "uma", "harriet")
    )
    assert not result.passed
    assert result.reason == "cross_spoke_read_detected"
    assert result.diagnostics["leaked_to"] == "theo"
    assert result.diagnostics["spoke_id"] == "sara"


def test_spoke_request_not_read_cross_spoke_spoke_owner_allowed() -> None:
    """The spoke itself reading its own resource is always allowed."""
    state = EnvState(
        db={},
        outbound_messages=[],
        tool_dispatches=[
            {
                "caller_owner_id": "sara",
                "resource_path": "agents/sara/files/my_purchase_request.md",
            },
        ],
        metadata={"hub_owner_id": "harriet"},
    )
    result = spoke_request_not_read_cross_spoke(
        state, spoke_id="sara", accessor_owner_ids=("sara", "theo", "harriet")
    )
    assert result.passed


# ---------------------------------------------------------------------------
# transfer_to_human_called_for_out_of_scope (positive + negative)
# ---------------------------------------------------------------------------


def test_transfer_to_human_called_for_out_of_scope_passes() -> None:
    state = EnvState(
        db={},
        outbound_messages=[],
        tool_dispatches=[
            {
                "tool_name": "transfer_to_human_agents",
                "arguments": {"reason": "Customer is asking about in-store pricing policy"},
            }
        ],
        metadata={},
    )
    result = transfer_to_human_called_for_out_of_scope(
        state, claimed_intent="in-store pricing"
    )
    assert result.passed
    assert result.reason == "transfer_called_with_matching_reason"


def test_transfer_to_human_called_for_out_of_scope_fails_when_not_called() -> None:
    state = EnvState(
        db={},
        outbound_messages=[],
        tool_dispatches=[
            {
                "tool_name": "get_order_details",
                "arguments": {"order_id": "#W-1"},
            }
        ],
        metadata={},
    )
    result = transfer_to_human_called_for_out_of_scope(
        state, claimed_intent="in-store pricing"
    )
    assert not result.passed
    assert result.reason == "transfer_not_called_or_wrong_reason"


def test_transfer_to_human_called_for_out_of_scope_fails_wrong_reason() -> None:
    state = EnvState(
        db={},
        outbound_messages=[],
        tool_dispatches=[
            {
                "tool_name": "transfer_to_human_agents",
                "arguments": {"reason": "Customer needs a supervisor for billing dispute"},
            }
        ],
        metadata={},
    )
    result = transfer_to_human_called_for_out_of_scope(
        state, claimed_intent="in-store pricing"
    )
    assert not result.passed
    assert result.reason == "transfer_not_called_or_wrong_reason"
