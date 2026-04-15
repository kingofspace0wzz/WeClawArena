from clawsocialarena.audit.phase_tracker import PhaseTracker
from clawsocialarena.types import SocialPhase


def test_starts_in_discovery():
    pt = PhaseTracker()
    assert pt.current_phase() == SocialPhase.DISCOVERY


def test_phase_schedule_from_gt():
    pt = PhaseTracker.from_schedule([
        {"phase": "discovery", "start_turn": 0, "end_turn": 2},
        {"phase": "negotiation", "start_turn": 2, "end_turn": 5},
    ])
    assert pt.current_phase() == SocialPhase.DISCOVERY
    pt.advance_to_turn(1)
    assert pt.current_phase() == SocialPhase.DISCOVERY
    pt.advance_to_turn(3)
    assert pt.current_phase() == SocialPhase.NEGOTIATION


def test_no_schedule_stays_in_discovery():
    pt = PhaseTracker()
    pt.advance_to_turn(99)
    assert pt.current_phase() == SocialPhase.DISCOVERY


def test_transitions_on_cue():
    pt = PhaseTracker()
    pt.observe_event("boundary_declared")
    assert pt.current_phase() == SocialPhase.BOUNDARY_SETTING
    pt.observe_event("repair_initiated")
    assert pt.current_phase() == SocialPhase.REPAIR
    pt.observe_event("unknown_cue")
    # Unknown cues leave phase unchanged
    assert pt.current_phase() == SocialPhase.REPAIR
