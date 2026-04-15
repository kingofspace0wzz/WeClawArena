"""Scheduling task family terminal predicate."""

from datetime import datetime


def _iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def scheduling_pinned_slot(*, state: dict, spec: dict) -> bool:
    slot = state.get("pinned_slot")
    if not slot:
        return False
    try:
        t = _iso(slot)
    except ValueError:
        return False
    window = spec["valid_window"]
    return _iso(window["start"]) <= t <= _iso(window["end"])
