"""PhaseTracker — tracks the current social phase for the runtime.

Phase 1.5 scope: minimal GT-schedule-driven advancement. Full Phase 2 version
(with cue observation and online phase detection) extends this.
"""

from __future__ import annotations

from clawsocialarena.types import SocialPhase


_CUES = {
    "boundary_declared": SocialPhase.BOUNDARY_SETTING,
    "disclosure_committed": SocialPhase.DISCLOSURE,
    "repair_initiated": SocialPhase.REPAIR,
    "negotiation_started": SocialPhase.NEGOTIATION,
    "discovery_started": SocialPhase.DISCOVERY,
}


class PhaseTracker:
    def __init__(self) -> None:
        self._phase = SocialPhase.DISCOVERY
        self._schedule: list[dict] | None = None
        self._turn = 0

    @classmethod
    def from_schedule(cls, schedule: list[dict]) -> "PhaseTracker":
        pt = cls()
        pt._schedule = schedule
        return pt

    def current_phase(self) -> SocialPhase:
        return self._phase

    def advance_to_turn(self, turn: int) -> None:
        self._turn = turn
        if not self._schedule:
            return
        for window in self._schedule:
            if window["start_turn"] <= turn < window["end_turn"]:
                try:
                    self._phase = SocialPhase(window["phase"])
                except ValueError:
                    continue
                return

    def observe_event(self, cue: str) -> None:
        if cue in _CUES:
            self._phase = _CUES[cue]
