"""wildclaw_social predicate library."""
from __future__ import annotations

from typing import Any, Mapping

from clawsocialarena.eval.predicates.types import EnvState, PredicateResult


def meeting_event_created(
    state: EnvState,
    meeting_id: str,
) -> PredicateResult:
    meetings = state.db.get("meetings", {})
    meeting = meetings.get(meeting_id)
    if meeting is None:
        return PredicateResult(passed=False, reason="meeting_not_found")
    if not int(meeting.get("event_created") or 0):
        return PredicateResult(passed=False, reason="event_not_created")
    return PredicateResult(passed=True, reason="event_created_ok")


def all_participants_confirmed_meeting(
    state: EnvState,
    meeting_id: str,
    expected_participants: list[str],
) -> PredicateResult:
    meetings = state.db.get("meetings", {})
    meeting = meetings.get(meeting_id)
    if meeting is None:
        return PredicateResult(passed=False, reason="meeting_not_found")
    confirmations = meeting.get("confirmations") or {}
    if not isinstance(confirmations, Mapping):
        return PredicateResult(passed=False, reason="confirmations_missing")
    missing = [p for p in expected_participants if not confirmations.get(p)]
    if missing:
        return PredicateResult(
            passed=False,
            reason="missing_confirmations",
            diagnostics={"missing": missing},
        )
    return PredicateResult(passed=True, reason="all_confirmed_ok")


PREDICATE_REGISTRY: dict[str, Any] = {
    "meeting_event_created": meeting_event_created,
    "all_participants_confirmed_meeting": all_participants_confirmed_meeting,
}
