"""MARBLE bargaining-negotiation family pack.

Source: ``knowledge/MARBLE/multiagentbench/bargaining/bargaining_main.jsonl``.
The native MARBLE bargaining tasks put 2-4 agents in a buyer/seller
mix; this v2 pack caps at 2 (one buyer, one seller) and reframes the
negotiation with explicit private-constraint privacy rules.

See ``docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md``
section 4.2 for the full design.
"""

from clawsocialarena.generator.family_packs.marble_bargaining.loader import (
    MarbleBargainingLoader,
    load_bargaining_scenario,
)
from clawsocialarena.generator.family_packs.marble_bargaining.materialize import (
    materialize_bargaining_bundle,
)


NATURALIZATION_HINTS: dict[str, object] = {
    "domain": "price negotiation over a discrete good",
    "tone": "two-party haggling, professional but adversarial, terse offers",
    "key_terms": [
        "buyer",
        "seller",
        "budget ceiling",
        "reservation price",
        "market reference",
        "offer",
        "counter-offer",
    ],
    "naturalization_focus": (
        "Make the item description, market reference, and offer cadence "
        "feel like real B2B or marketplace negotiation. The privacy rule "
        "(buyer's budget ceiling and seller's reservation price are "
        "private; neither agent should reveal their own constraint "
        "casually) MUST stay visible in personas. The deal-window rule "
        "(accept blocked if price violates the accepter's own constraint) "
        "is enforced by handlers; the naturalization should not encourage "
        "agents to ignore it."
    ),
}


__all__ = [
    "MarbleBargainingLoader",
    "load_bargaining_scenario",
    "materialize_bargaining_bundle",
    "NATURALIZATION_HINTS",
]
