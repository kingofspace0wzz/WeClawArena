"""MARBLE bargaining owned-ecosystem family pack."""

from clawsocialarena.generator.family_packs.marble_bargaining.loader import (
    MarbleBargainingLoader,
    load_bargaining_scenario,
)
from clawsocialarena.generator.family_packs.marble_bargaining.materialize import (
    materialize_bargaining_bundle,
)


NATURALIZATION_HINTS: dict[str, object] = {
    "domain": "owned-ecosystem procurement negotiation",
    "tone": "professional procurement, sales, and finance coordination",
    "key_terms": [
        "purchase request",
        "budget ledger",
        "approval rule",
        "inventory",
        "price book",
        "purchase order",
        "seller order",
        "approval log",
    ],
    "naturalization_focus": (
        "Keep each owner ecosystem meaningful. Agents must consult their "
        "owned files and databases before negotiating, approving, or closing. "
        "Do not reduce the task to a simple buyer budget and seller reservation."
    ),
}


__all__ = [
    "MarbleBargainingLoader",
    "load_bargaining_scenario",
    "materialize_bargaining_bundle",
    "NATURALIZATION_HINTS",
]
