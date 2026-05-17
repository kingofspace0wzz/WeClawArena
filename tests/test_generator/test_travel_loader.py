"""Tests for the travel loader (Task 3 of the travel first-ship plan)."""
from __future__ import annotations

import pytest

from clawsocialarena.generator.family_packs.travel.loader import (
    TravelScenarioBundle,
    load_travel_scenario,
)
from clawsocialarena.scenario.models import CoordinationMode


# --- CU-D-travel: triad shape (traveler + partner_hotel + approver) ----------


def test_load_travel_cu_returns_triad() -> None:
    bundle = load_travel_scenario(
        trip_id="TRIP-CU-OE-001",
        resource_profile="owned_ecosystem_solo_business_yunnan",
    )
    assert isinstance(bundle, TravelScenarioBundle)
    scn = bundle.scenario
    assert scn.coordination_mode == CoordinationMode.GRAPH
    assert scn.family_id == "travel"
    assert scn.category == "CU"
    assert len(scn.agents) == 3
    assert len(scn.agent_graph.nodes) == 3
    role_labels = {n.role_label for n in scn.agent_graph.nodes}
    assert role_labels == {"traveler", "partner_hotel", "approver"}


def test_load_travel_cu_owner_ids_are_unique() -> None:
    bundle = load_travel_scenario(
        trip_id="TRIP-CU-OE-001",
        resource_profile="owned_ecosystem_solo_business_yunnan",
    )
    owner_ids = [n.owner_id for n in bundle.scenario.agent_graph.nodes]
    assert len(owner_ids) == len(set(owner_ids))


def test_load_travel_cu_edges_wire_negotiation_and_approval() -> None:
    bundle = load_travel_scenario(
        trip_id="TRIP-CU-OE-001",
        resource_profile="owned_ecosystem_solo_business_yunnan",
    )
    edges = bundle.scenario.agent_graph.edges
    relationships = {(e.source, e.target, e.relationship, e.channel) for e in edges}
    traveler = bundle.traveler_agent_id
    partner = bundle.partner_hotel_agent_id
    approver = bundle.approver_agent_id
    assert (traveler, partner, "negotiates_with", "booking_dm") in relationships
    assert (partner, traveler, "sends_order_terms_to", "booking_dm") in relationships
    assert (traveler, approver, "requests_approval_from", "approval_dm") in relationships
    assert (approver, traveler, "approves_purchase_for", "approval_dm") in relationships


def test_load_travel_cu_initial_state_carries_trip_meta() -> None:
    bundle = load_travel_scenario(
        trip_id="TRIP-CU-OE-001",
        resource_profile="owned_ecosystem_solo_business_yunnan",
    )
    st = bundle.scenario.initial_state
    assert st["trip_id"] == "TRIP-CU-OE-001"
    assert st["resource_profile"] == "owned_ecosystem_solo_business_yunnan"
    assert st["destination"]
    assert "date_window" in st
    assert "target_unit_rate" in st
    assert "room_type_target" in st


def test_load_travel_cu_opening_message_goes_to_traveler() -> None:
    bundle = load_travel_scenario(
        trip_id="TRIP-CU-OE-001",
        resource_profile="owned_ecosystem_solo_business_yunnan",
    )
    om = bundle.scenario.opening_message
    assert om["to"] == bundle.traveler_agent_id
    assert om["from"] == "system"
    assert "TRIP-CU-OE-001" in om["content"]


# --- MG-C-travel: group shape (organizer + 3 co_travelers + partner_hotel) ---


def test_load_travel_mg_returns_five_agents() -> None:
    bundle = load_travel_scenario(
        trip_id="TRIP-MG-OE-101",
        resource_profile="owned_ecosystem_family_group_guizhou",
    )
    scn = bundle.scenario
    assert scn.coordination_mode == CoordinationMode.GRAPH
    assert scn.category == "MG"
    assert len(scn.agents) == 5
    assert len(scn.agent_graph.nodes) == 5
    role_labels = sorted(n.role_label for n in scn.agent_graph.nodes)
    assert role_labels == [
        "co_traveler",
        "co_traveler",
        "co_traveler",
        "organizer",
        "partner_hotel",
    ]


def test_load_travel_mg_owner_ids_are_unique() -> None:
    """Critical topology constraint: every agent has a distinct owner_id.

    This catches the persona-aliasing failure mode that batch 0074
    surfaced for legacy HS/MG templates.
    """
    bundle = load_travel_scenario(
        trip_id="TRIP-MG-OE-101",
        resource_profile="owned_ecosystem_family_group_guizhou",
    )
    owner_ids = [n.owner_id for n in bundle.scenario.agent_graph.nodes]
    assert len(owner_ids) == len(set(owner_ids))


def test_load_travel_mg_has_group_dm_mesh_plus_booking_edge() -> None:
    bundle = load_travel_scenario(
        trip_id="TRIP-MG-OE-101",
        resource_profile="owned_ecosystem_family_group_guizhou",
    )
    edges = bundle.scenario.agent_graph.edges
    group_dm_edges = [e for e in edges if e.channel == "group_dm"]
    # Organizer + 3 co-travelers = 4 agents; full mesh = 4*3 = 12 directed edges
    assert len(group_dm_edges) == 12
    booking_dm_edges = [e for e in edges if e.channel == "booking_dm"]
    # Organizer <-> partner_hotel in both directions
    assert len(booking_dm_edges) == 2


def test_load_travel_mg_initial_state_carries_group_context() -> None:
    bundle = load_travel_scenario(
        trip_id="TRIP-MG-OE-101",
        resource_profile="owned_ecosystem_family_group_guizhou",
    )
    st = bundle.scenario.initial_state
    assert st["trip_id"] == "TRIP-MG-OE-101"
    assert st["group_budget_envelope"] == 8000.0
    assert st["per_person_cap"] == 2200.0
    assert st["consensus_threshold"] == 4


def test_load_travel_mg_opening_message_goes_to_organizer() -> None:
    bundle = load_travel_scenario(
        trip_id="TRIP-MG-OE-101",
        resource_profile="owned_ecosystem_family_group_guizhou",
    )
    om = bundle.scenario.opening_message
    assert om["to"] == bundle.organizer_agent_id


# --- Cross-cell invariants ---------------------------------------------------


def test_load_travel_bundle_exposes_evaluation_criteria_with_canonical_schema() -> None:
    bundle = load_travel_scenario(
        trip_id="TRIP-CU-OE-001",
        resource_profile="owned_ecosystem_solo_business_yunnan",
    )
    ec = bundle.evaluation_criteria
    allowed_keys = {
        "actions",
        "env_assertions",
        "communicate_info",
        "nl_assertions",
        "reward_basis",
    }
    assert set(ec.keys()).issubset(allowed_keys)
    assert "database_writes" not in ec  # legacy key, must not appear
    assert ec["reward_basis"] in {"actions", "env_assertions", "mixed"}


def test_load_travel_bundle_phase_schedule_present() -> None:
    bundle = load_travel_scenario(
        trip_id="TRIP-CU-OE-001",
        resource_profile="owned_ecosystem_solo_business_yunnan",
    )
    assert bundle.phase_schedule
    phases = [p.get("name") for p in bundle.phase_schedule]
    # discovery -> negotiation -> consent -> commitment per the family-pack spec
    assert "discovery" in phases
    assert "commitment" in phases


def test_load_travel_unknown_trip_id_raises_helpful_error() -> None:
    with pytest.raises(KeyError) as excinfo:
        load_travel_scenario(
            trip_id="TRIP-DOES-NOT-EXIST",
            resource_profile="owned_ecosystem_nope",
        )
    assert "TRIP-DOES-NOT-EXIST" in str(excinfo.value)


def test_persona_system_prompts_reference_correct_owner_ids() -> None:
    bundle = load_travel_scenario(
        trip_id="TRIP-CU-OE-001",
        resource_profile="owned_ecosystem_solo_business_yunnan",
    )
    by_role = {n.role_label: n for n in bundle.scenario.agent_graph.nodes}
    agents_by_id = {a.agent_id: a for a in bundle.scenario.agents}
    traveler_node = by_role["traveler"]
    traveler_agent = agents_by_id[traveler_node.agent_id]
    assert traveler_node.owner_id in traveler_agent.system_prompt_template


def test_delegate_authorization_code_appears_in_traveler_prompt() -> None:
    bundle = load_travel_scenario(
        trip_id="TRIP-CU-OE-001",
        resource_profile="owned_ecosystem_solo_business_yunnan",
    )
    agents_by_id = {a.agent_id: a for a in bundle.scenario.agents}
    traveler_prompt = agents_by_id[bundle.traveler_agent_id].system_prompt_template
    assert "TRIP-CU-OE-001-DELEGATE-AUTH" in traveler_prompt
