"""WildClawBench Social-Interaction family pack.

Source: ``knowledge/WildClawBench/tasks/03_Social_Interaction/``. The
canonical task is a multi-round meeting-time negotiation across a
director and three participants. The single-agent + mocked-participants
shape is reframed as a 4-agent star graph (director hub + three peers)
with in-process Gmail/Calendar via per-agent SQLite. The spec-mandated
FastAPI mock services land in a later phase; the in-process version
proves the family-pack contract.

See ``docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md``
section 4.3 for the full design.
"""

from clawsocialarena.generator.family_packs.wildclaw_social.loader import (
    WildClawSocialLoader,
    load_meeting_negotiation_scenario,
)
from clawsocialarena.generator.family_packs.wildclaw_social.materialize import (
    materialize_meeting_negotiation_bundle,
)


NATURALIZATION_HINTS: dict[str, object] = {
    "domain": "corporate meeting scheduling across timezones",
    "tone": "executive-assistant correspondence, formal email register",
    "key_terms": [
        "meeting",
        "calendar availability",
        "timezone",
        "conference room",
        "participant confirmation",
        "scheduling conflict",
        "director request",
    ],
    "naturalization_focus": (
        "Make the meeting purpose, room options, and participant identities "
        "feel like real corporate scheduling. The authorization rule (the "
        "organizer cannot create the calendar event until every participant "
        "has explicitly confirmed attendance; participants can only check "
        "their own calendars) MUST stay visible. Calendar availability "
        "MUST use absolute dates inside the valid window, not relative "
        "phrases like 'next week'."
    ),
}


__all__ = [
    "WildClawSocialLoader",
    "load_meeting_negotiation_scenario",
    "materialize_meeting_negotiation_bundle",
    "NATURALIZATION_HINTS",
]
