"""Tests for the tau2_retail family pack loader.

Validates the Phase 3 skeleton: the loader reads tau2 retail fixtures
and produces a v2 Scenario populated with coordination_mode,
agent_graph, and a tau2-style evaluation_criteria block. Per
docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md
section 4.4.
"""
from __future__ import annotations

import pytest

from clawsocialarena.generator.family_packs.tau2_retail import (
    SharedAccountLoader,
    load_shared_account_scenario,
)
from clawsocialarena.generator.scenario_validator import validate_scenario
from clawsocialarena.scenario.models import CoordinationMode


def test_loader_produces_two_agent_household_scenario() -> None:
    bundle = load_shared_account_scenario()
    scenario = bundle.scenario

    assert scenario.family_id == "tau2_retail"
    assert scenario.coordination_mode == CoordinationMode.GRAPH
    assert scenario.agent_graph is not None
    assert len(scenario.agent_graph.nodes) == 2
    agent_ids = {node.agent_id for node in scenario.agent_graph.nodes}
    assert agent_ids == {"alice_assistant", "bob_assistant"}


def test_loader_distinguishes_primary_and_secondary_roles() -> None:
    bundle = load_shared_account_scenario()
    graph = bundle.scenario.agent_graph
    assert graph is not None

    roles = {node.agent_id: node.role_label for node in graph.nodes}
    assert roles["alice_assistant"] == "primary_account_holder"
    assert roles["bob_assistant"] == "secondary_account_holder"

    mandates = {
        node.agent_id: node.approval_mandate for node in graph.nodes
    }
    assert mandates["alice_assistant"] == "self"
    assert mandates["bob_assistant"] == "primary_holder_required"


def test_loader_evaluation_criteria_uses_composite_reward_basis() -> None:
    bundle = load_shared_account_scenario()

    assert bundle.evaluation_criteria["reward_basis"] == "COMPOSITE"
    predicates = {
        a["predicate"] for a in bundle.evaluation_criteria["env_assertions"]
    }
    assert predicates == {
        "household_order_finalized_for",
        "household_payment_authorized_by",
        "shipping_address_is_household_owned",
    }


def test_loader_evaluation_criteria_resolves_through_predicate_registry() -> None:
    """Every predicate name in evaluation_criteria must resolve against
    the family pack's predicate registry. This catches drift between
    the loader and the predicate module."""
    from clawsocialarena.eval.predicates.tau2_retail import PREDICATE_REGISTRY

    bundle = load_shared_account_scenario()
    for assertion in bundle.evaluation_criteria["env_assertions"]:
        name = assertion["predicate"]
        assert name in PREDICATE_REGISTRY, (
            f"evaluation_criteria references {name!r} but it is not "
            f"registered in PREDICATE_REGISTRY"
        )


def test_loader_passes_scenario_validator() -> None:
    """The generated scenario must satisfy the topology validator's
    structural rules."""
    bundle = load_shared_account_scenario()
    result = validate_scenario(bundle.scenario)
    assert result.passed, result.errors


def test_loader_phase_schedule_has_four_phases() -> None:
    bundle = load_shared_account_scenario()
    phases = [p["phase"] for p in bundle.phase_schedule]
    assert phases == ["discovery", "negotiation", "approval", "commitment"]


def test_loader_declares_resource_ids_under_household_namespace() -> None:
    bundle = load_shared_account_scenario()
    assert any("household.HH-7.orders" in rid for rid in bundle.declared_resource_ids)


def test_predicate_household_order_finalized_for() -> None:
    """Smoke test: the predicate returns pass on a finalized order and
    fail on the various error cases."""
    from clawsocialarena.eval.predicates.tau2_retail import (
        household_order_finalized_for,
    )
    from clawsocialarena.eval.predicates.types import EnvState

    state = EnvState(
        db={
            "orders": {
                "#W2378156": {
                    "household_id": "HH-7",
                    "status": "finalized",
                },
                "#W9999999": {
                    "household_id": "HH-7",
                    "status": "pending",
                },
                "#W8888888": {
                    "household_id": "HH-OTHER",
                    "status": "finalized",
                },
            }
        }
    )

    ok = household_order_finalized_for(
        state, order_id="#W2378156", household_id="HH-7"
    )
    assert ok.passed

    missing = household_order_finalized_for(
        state, order_id="#W0000000", household_id="HH-7"
    )
    assert not missing.passed
    assert "not_found" in missing.reason

    wrong_household = household_order_finalized_for(
        state, order_id="#W8888888", household_id="HH-7"
    )
    assert not wrong_household.passed
    assert "household_mismatch" in wrong_household.reason

    not_final = household_order_finalized_for(
        state, order_id="#W9999999", household_id="HH-7"
    )
    assert not not_final.passed
    assert "status_not_finalized" in not_final.reason
