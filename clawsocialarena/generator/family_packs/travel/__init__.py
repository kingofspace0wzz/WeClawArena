"""Travel family pack.

Source: TravelBench (ACL 2026, ``knowledge/TravelBench/``). Single-agent
travel tool-use data lifted into English and reframed as either a
CU-D-travel triad (traveler + partner_hotel + approver) or an
MG-C-travel group (organizer + 3 co-travelers + partner_hotel) per the
family-pack-design spec section 4.7.

This module exposes the family entry points the registry imports.
"""
from __future__ import annotations

from clawsocialarena.generator.family_packs.travel.loader import (
    TravelScenarioBundle,
    load_travel_scenario,
)
from clawsocialarena.generator.family_packs.travel.materialize import (
    materialize_travel_bundle,
)


NATURALIZATION_HINTS: dict = {
    "domain": "travel coordination (hotel booking, group itinerary, partner negotiation)",
    "tone": "polite professional with traveler-side warmth; partner side is sales-leaning",
    "key_terms": [
        "trip_id",
        "loyalty tier",
        "deluxe king",
        "family suite",
        "delegate authorization code",
        "shared breakfast",
        "check-in window",
        "RevPAR",
        "partner network",
        "ADR",
    ],
    "naturalization_focus": (
        "Travel scenarios are time-bounded and location-specific. "
        "Naturalized text should reference the destination city, "
        "check-in / check-out dates, and partner-specific room types. "
        "Avoid generic e-commerce framing; keep the hotel-booking voice."
    ),
}


__all__ = [
    "TravelScenarioBundle",
    "load_travel_scenario",
    "materialize_travel_bundle",
    "NATURALIZATION_HINTS",
]
