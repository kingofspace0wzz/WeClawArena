"""MARBLE bidding family pack."""

from clawsocialarena.generator.family_packs.marble_bidding.loader import (
    BiddingScenarioBundle,
    MarbleBiddingLoader,
    load_bidding_scenario,
)
from clawsocialarena.generator.family_packs.marble_bidding.materialize import (
    materialize_bidding_bundle,
)


NATURALIZATION_HINTS: dict[str, object] = {
    "domain": "multi-buyer bidding over a discrete good",
    "tone": "competitive marketplace bidding with terse public price moves",
    "key_terms": [
        "seller",
        "buyer",
        "bid",
        "public bid log",
        "reservation price",
        "budget ceiling",
        "buyer confirmation",
    ],
    "naturalization_focus": (
        "Keep seller reservation constraints, buyer budget ceilings, and bid "
        "strategy notes private. The public state is the auction listing and bid "
        "log. A valid deal requires at least two bidders, seller award, winning "
        "buyer confirmation, and consistent buyer/seller close artifacts."
    ),
}


__all__ = [
    "BiddingScenarioBundle",
    "MarbleBiddingLoader",
    "load_bidding_scenario",
    "materialize_bidding_bundle",
    "NATURALIZATION_HINTS",
]
