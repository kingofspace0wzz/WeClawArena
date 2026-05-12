"""Tau2 airline family pack.

Source: ``knowledge/tau2-bench/data/tau2/domains/airline/``. The single-
passenger airline flow is reframed as a group booking with an organizer
plus one traveler-passenger; the family pack produces a v2 scenario
with a two-node agent_graph and coordination_mode=graph.

See ``docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md``
section 4.6 for the full design.
"""

from clawsocialarena.generator.family_packs.tau2_airline.loader import (
    Tau2AirlineLoader,
    load_group_seat_change_scenario,
)
from clawsocialarena.generator.family_packs.tau2_airline.materialize import (
    materialize_group_booking_bundle,
)


NATURALIZATION_HINTS: dict[str, object] = {
    "domain": "airline travel",
    "tone": "travel-coordinator assistant, methodical, deferential about per-passenger choices",
    "key_terms": [
        "group booking",
        "organizer",
        "traveler",
        "reservation",
        "seat change",
        "passenger consent",
        "baggage allocation",
    ],
    "naturalization_focus": (
        "Make flights, seat assignments, and itineraries feel like real "
        "airline bookings. The consent rule (per-passenger seat / baggage "
        "/ meal changes require that passenger's explicit consent before "
        "the organizer commits) MUST be visible in the opening message and "
        "persona notes -- the organizer cannot finalize changes on behalf "
        "of another passenger."
    ),
}


__all__ = [
    "Tau2AirlineLoader",
    "load_group_seat_change_scenario",
    "materialize_group_booking_bundle",
    "NATURALIZATION_HINTS",
]
