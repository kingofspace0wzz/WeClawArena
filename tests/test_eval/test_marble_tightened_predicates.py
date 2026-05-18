"""Unit tests for tightened MARBLE-derived deterministic predicates.

- ``marble_research.proposal_has_at_least_one_unpublished_citation``:
  closes the vacuous-truth where ``citations=[]`` trivially satisfies
  ``proposal_citations_authorized``.
- ``marble_bargaining`` owned-ecosystem predicates: verify purchase
  order, seller order, finance approval, artifact consistency, and
  owned resource constraints.
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


def _owned_bargaining_state() -> EnvState:
    return EnvState(
        db={
            "negotiation_state": {
                "TXN-OE-001": {
                    "transaction_id": "TXN-OE-001",
                    "item_id": "PRINTER-BUNDLE-12",
                    "purchase_order": {
                        "po_id": "PO-TXN-OE-001",
                        "transaction_id": "TXN-OE-001",
                        "item_id": "PRINTER-BUNDLE-12",
                        "seller_owner_id": "northstar_sales",
                        "quantity": 12,
                        "unit_price": 795.0,
                        "warranty_months": 24,
                        "approval_id": "APR-TXN-OE-001",
                    },
                    "seller_acceptance": {
                        "order_id": "SO-TXN-OE-001",
                        "transaction_id": "TXN-OE-001",
                        "item_id": "PRINTER-BUNDLE-12",
                        "buyer_owner_id": "acme_procurement",
                        "quantity": 12,
                        "unit_price": 795.0,
                        "warranty_months": 24,
                        "approval_id": "APR-TXN-OE-001",
                    },
                }
            },
            "approval_log": {
                "APR-TXN-OE-001": {
                    "approval_id": "APR-TXN-OE-001",
                    "transaction_id": "TXN-OE-001",
                    "item_id": "PRINTER-BUNDLE-12",
                    "quantity": 12,
                    "unit_price": 795.0,
                    "warranty_months": 24,
                }
            },
            "budget_ledger": {
                "manufacturing_ops": {
                    "remaining_budget": 10400.0,
                    "protected": 1,
                }
            },
            "price_book": {
                "PRINTER-BUNDLE-12": {
                    "minimum_unit_price": 760.0,
                    "warranty_24_month_min_price": 790.0,
                }
            },
        }
    )


def test_owned_ecosystem_predicates_pass_for_consistent_transaction() -> None:
    from clawsocialarena.eval.predicates.marble_bargaining import (
        approval_log_recorded,
        price_within_owned_constraints,
        purchase_order_recorded,
        seller_order_recorded,
        transaction_artifacts_consistent,
    )

    state = _owned_bargaining_state()
    assert purchase_order_recorded(state, "TXN-OE-001").passed
    assert seller_order_recorded(state, "TXN-OE-001").passed
    assert approval_log_recorded(state, "TXN-OE-001").passed
    assert transaction_artifacts_consistent(state, "TXN-OE-001").passed
    assert price_within_owned_constraints(state, "TXN-OE-001").passed


def test_inventory_allocation_feasible_passes_when_movable_hold_covers_quantity() -> None:
    from clawsocialarena.eval.predicates.marble_bargaining import (
        inventory_allocation_feasible,
    )

    state = EnvState(
        db={
            "negotiation_state": {
                "TXN-OE-101": {
                    "purchase_order": {
                        "transaction_id": "TXN-OE-101",
                        "item_id": "THERMAL-SCANNER-KIT-24",
                        "quantity": 24,
                    }
                }
            },
            "inventory": {
                "THERMAL-SCANNER-KIT-24": {
                    "item_id": "THERMAL-SCANNER-KIT-24",
                    "available_quantity": 30,
                    "reserved_quantity": 10,
                }
            },
            "inventory_allocations": {
                "ALLOC-LOW-08": {
                    "item_id": "THERMAL-SCANNER-KIT-24",
                    "quantity": 4,
                    "movable": 1,
                }
            },
        }
    )
    result = inventory_allocation_feasible(state, "TXN-OE-101")
    assert result.passed is True


def test_shipping_terms_consistent_requires_matching_terms() -> None:
    from clawsocialarena.eval.predicates.marble_bargaining import (
        shipping_terms_consistent,
    )

    state = _owned_bargaining_state()
    terms = {
        "delivery_date": "2026-06-12",
        "shipping_method": "cold_chain_freight",
        "temperature_range": "2C-8C",
    }
    state.db["negotiation_state"]["TXN-OE-001"]["purchase_order"]["terms"] = dict(terms)
    state.db["negotiation_state"]["TXN-OE-001"]["seller_acceptance"]["terms"] = dict(
        terms
    )
    state.db["approval_log"]["APR-TXN-OE-001"]["terms"] = dict(terms)

    result = shipping_terms_consistent(state, "TXN-OE-001")
    assert result.passed is True


def test_shipping_terms_consistent_accepts_decoded_terms_json_mapping() -> None:
    from clawsocialarena.eval.predicates.marble_bargaining import (
        shipping_terms_consistent,
    )

    state = _owned_bargaining_state()
    terms = {
        "delivery_date": "2026-06-12",
        "shipping_method": "cold_chain_freight",
        "temperature_range": "2C-8C",
    }
    state.db["negotiation_state"]["TXN-OE-001"]["purchase_order"]["terms"] = dict(terms)
    state.db["negotiation_state"]["TXN-OE-001"]["seller_acceptance"]["terms"] = dict(
        terms
    )
    state.db["approval_log"]["APR-TXN-OE-001"]["terms_json"] = dict(terms)

    result = shipping_terms_consistent(state, "TXN-OE-001")
    assert result.passed is True


def test_shipping_terms_consistent_fails_on_empty_required_value() -> None:
    from clawsocialarena.eval.predicates.marble_bargaining import (
        shipping_terms_consistent,
    )

    state = _owned_bargaining_state()
    terms = {
        "delivery_date": "",
        "shipping_method": "cold_chain_freight",
        "temperature_range": "2C-8C",
    }
    state.db["negotiation_state"]["TXN-OE-001"]["purchase_order"]["terms"] = dict(terms)
    state.db["negotiation_state"]["TXN-OE-001"]["seller_acceptance"]["terms"] = dict(
        terms
    )
    state.db["approval_log"]["APR-TXN-OE-001"]["terms"] = dict(terms)

    result = shipping_terms_consistent(state, "TXN-OE-001")
    assert result.passed is False
    assert result.reason == "delivery_date_missing"


def test_prior_contract_terms_consistent_requires_matching_terms() -> None:
    from clawsocialarena.eval.predicates.marble_bargaining import (
        prior_contract_terms_consistent,
    )

    state = _owned_bargaining_state()
    terms = {
        "prior_contract_id": "MSA-ACME-2025",
        "support_tier": "premium",
        "coterm_end_date": "2027-05-31",
    }
    state.db["negotiation_state"]["TXN-OE-001"]["purchase_order"]["terms"] = dict(terms)
    state.db["negotiation_state"]["TXN-OE-001"]["seller_acceptance"]["terms"] = dict(
        terms
    )
    state.db["approval_log"]["APR-TXN-OE-001"]["terms"] = dict(terms)

    result = prior_contract_terms_consistent(state, "TXN-OE-001")
    assert result.passed is True


def test_required_terms_consistent_accepts_profile_specific_keys() -> None:
    from clawsocialarena.eval.predicates.marble_bargaining import (
        required_terms_consistent,
    )

    state = _owned_bargaining_state()
    terms = {
        "broker_id": "BRK-CB-ANCHOR-2026",
        "commission_rate": "0.035",
        "broker_authorization_id": "CB-BROKER-AUTH-109",
    }
    state.db["negotiation_state"]["TXN-OE-001"]["purchase_order"]["terms"] = dict(terms)
    state.db["negotiation_state"]["TXN-OE-001"]["seller_acceptance"]["terms"] = dict(
        terms
    )
    state.db["approval_log"]["APR-TXN-OE-001"]["terms"] = dict(terms)

    result = required_terms_consistent(
        state,
        "TXN-OE-001",
        ["broker_id", "commission_rate", "broker_authorization_id"],
    )
    assert result.passed is True


def test_required_terms_consistent_is_registered_for_env_assertions() -> None:
    from clawsocialarena.eval.predicates.marble_bargaining import PREDICATE_REGISTRY

    assert "required_terms_consistent" in PREDICATE_REGISTRY


def test_owned_ecosystem_constraints_fail_when_total_exceeds_budget() -> None:
    from clawsocialarena.eval.predicates.marble_bargaining import (
        price_within_owned_constraints,
    )

    state = _owned_bargaining_state()
    state.db["negotiation_state"]["TXN-OE-001"]["purchase_order"][
        "unit_price"
    ] = 900.0
    state.db["negotiation_state"]["TXN-OE-001"]["seller_acceptance"][
        "unit_price"
    ] = 900.0
    state.db["approval_log"]["APR-TXN-OE-001"]["unit_price"] = 900.0
    result = price_within_owned_constraints(state, "TXN-OE-001")
    assert result.passed is False
    assert result.reason == "total_price_exceeds_budget"
