"""Tests for the tau2_airline family pack loader."""
from __future__ import annotations

from clawsocialarena.generator.family_packs.tau2_airline import (
    Tau2AirlineLoader,
    load_group_seat_change_scenario,
)
from clawsocialarena.scenario.models import CoordinationMode


def test_scenario_has_two_node_graph_and_family_id() -> None:
    bundle = load_group_seat_change_scenario()
    assert bundle.scenario.family_id == "tau2_airline"
    assert bundle.scenario.coordination_mode == CoordinationMode.GRAPH
    assert bundle.scenario.agent_graph is not None
    assert len(bundle.scenario.agent_graph.nodes) == 2
    organizer = next(
        n for n in bundle.scenario.agent_graph.nodes if n.role_label == "group_organizer"
    )
    traveler = next(
        n for n in bundle.scenario.agent_graph.nodes if n.role_label == "group_traveler"
    )
    assert organizer.owner_id == "alice"
    assert traveler.owner_id == "bob"
    assert organizer.approval_mandate == "self"
    assert traveler.approval_mandate == "self"


def test_evaluation_criteria_references_seeded_reservation() -> None:
    loader = Tau2AirlineLoader()
    bundle = loader.load_group_seat_change()
    # The target reservation must be one tau2 ships in db.json so that
    # the materializer's seed and the assertion can resolve it.
    seeded = list(loader._load_db().get("reservations", {}).keys())
    assert seeded, "tau2 airline db.json should ship reservations"
    target = bundle.evaluation_criteria["env_assertions"][0]["args"]["reservation_id"]
    assert target == seeded[0]


def test_evaluation_criteria_consent_arg_is_traveler_owner_id() -> None:
    bundle = load_group_seat_change_scenario()
    consent_assertion = next(
        a
        for a in bundle.evaluation_criteria["env_assertions"]
        if a["predicate"] == "passenger_consented_to_change"
    )
    assert consent_assertion["args"]["passenger_id"] == "bob"


def test_phase_schedule_has_consent_phase() -> None:
    bundle = load_group_seat_change_scenario()
    phases = [phase["phase"] for phase in bundle.phase_schedule]
    assert "consent" in phases


def test_loader_kwargs_propagate_to_scenario() -> None:
    bundle = load_group_seat_change_scenario(
        organizer_owner="carol",
        traveler_owner="dave",
        group_id="GRP-99",
    )
    assert bundle.scenario.initial_state["group_id"] == "GRP-99"
    owners = {n.owner_id for n in bundle.scenario.agent_graph.nodes}
    assert owners == {"carol", "dave"}
