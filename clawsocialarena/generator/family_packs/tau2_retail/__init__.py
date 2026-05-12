"""Tau2 retail family pack.

Source: ``knowledge/tau2-bench/data/tau2/domains/retail/``. The single-
user retail flow is reframed as a household account with a primary
holder plus one secondary member; the family pack produces a v2
scenario with a two-node agent_graph and coordination_mode=graph.

See ``docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md``
section 4.4 for the full design.
"""

from clawsocialarena.generator.family_packs.tau2_retail.loader import (
    Tau2RetailLoader,
    load_household_exchange_scenario,
)
from clawsocialarena.generator.family_packs.tau2_retail.materialize import (
    materialize_household_bundle,
)


NATURALIZATION_HINTS: dict[str, object] = {
    "domain": "online retail",
    "tone": "customer-service assistant, polite, transaction-focused",
    "key_terms": [
        "household account",
        "primary holder",
        "secondary member",
        "order",
        "exchange",
        "payment authorization",
        "shipping address",
    ],
    "naturalization_focus": (
        "Make orders, items, prices, and addresses feel like real retail "
        "transactions. The authorization rule (only the primary holder may "
        "commit payment-touching changes; secondaries must explicitly "
        "consent to changes on their own line of the order) MUST remain "
        "intact in the naturalized opening message and persona notes."
    ),
}


__all__ = [
    "Tau2RetailLoader",
    "load_household_exchange_scenario",
    "materialize_household_bundle",
    "NATURALIZATION_HINTS",
]
