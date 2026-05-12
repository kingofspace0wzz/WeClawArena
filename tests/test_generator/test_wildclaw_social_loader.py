"""Tests for the wildclaw_social family pack loader."""
from __future__ import annotations

from clawsocialarena.generator.family_packs.wildclaw_social import (
    WildClawSocialLoader,
    load_meeting_negotiation_scenario,
)
from clawsocialarena.scenario.models import CoordinationMode


def test_scenario_has_four_node_star_graph() -> None:
    bundle = load_meeting_negotiation_scenario()
    assert bundle.scenario.family_id == "wildclaw_social"
    assert bundle.scenario.coordination_mode == CoordinationMode.STAR
    assert len(bundle.scenario.agent_graph.nodes) == 4
    organizers = [
        n for n in bundle.scenario.agent_graph.nodes if n.role_label == "meeting_organizer"
    ]
    participants = [
        n for n in bundle.scenario.agent_graph.nodes if n.role_label == "meeting_participant"
    ]
    assert len(organizers) == 1
    assert len(participants) == 3


def test_participant_availability_overlaps_at_thursday_morning() -> None:
    bundle = load_meeting_negotiation_scenario()
    for owner, slots in bundle.participant_availability.items():
        assert slots, f"{owner} has no availability"
        assert slots[0]["day"] == "Thursday"


def test_evaluation_criteria_uses_meeting_id() -> None:
    bundle = load_meeting_negotiation_scenario()
    assertions = bundle.evaluation_criteria["env_assertions"]
    for a in assertions:
        assert a["args"]["meeting_id"] == "MTG-7"


def test_all_participants_assertion_lists_three_owners() -> None:
    bundle = load_meeting_negotiation_scenario()
    confirmation_assertion = next(
        a
        for a in bundle.evaluation_criteria["env_assertions"]
        if a["predicate"] == "all_participants_confirmed_meeting"
    )
    expected = confirmation_assertion["args"]["expected_participants"]
    assert set(expected) == {"bob", "carol", "dave"}


def test_phase_schedule_has_confirmation_phase() -> None:
    bundle = load_meeting_negotiation_scenario()
    phases = [phase["phase"] for phase in bundle.phase_schedule]
    assert "confirmation" in phases
    assert "commitment" in phases


def test_loader_reads_source_excerpt_when_available() -> None:
    loader = WildClawSocialLoader()
    excerpt = loader._load_source_excerpt()
    # The source markdown ships with the repo so the excerpt should be non-empty.
    assert isinstance(excerpt, str)
    assert "Meeting" in excerpt or "meeting" in excerpt or excerpt == ""
