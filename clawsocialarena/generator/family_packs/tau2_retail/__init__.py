"""tau2 Retail owned-ecosystem family pack."""

from clawsocialarena.generator.family_packs.tau2_retail.loaders import (
    CrossAccountLoader,
    CrossAccountScenarioBundle,
    HubAggregatorLoader,
    HubAggregatorScenarioBundle,
    SharedAccountLoader,
    StoreRepDyadLoader,
    StoreRepDyadScenarioBundle,
    load_cross_account_scenario,
    load_hub_aggregator_scenario,
    load_shared_account_scenario,
    load_store_rep_dyad_scenario,
)
from clawsocialarena.generator.family_packs.tau2_retail.materialize import (
    materialize_cross_account_bundle,
    materialize_shared_account_bundle,
    materialize_store_rep_dyad_bundle,
)

# Compatibility aliases for code still importing the old household-only names.
# These will be removed once all call sites migrate (target: end of Phase 6).
Tau2RetailLoader = SharedAccountLoader
load_household_exchange_scenario = load_shared_account_scenario
materialize_household_bundle = materialize_shared_account_bundle

NATURALIZATION_HINTS: dict[str, object] = {
    "domain": "consumer retail owned-ecosystem coordination",
    "tone": "household, gift-giving, store-service, and family-plan coordination",
    "key_terms": [
        "payment method",
        "shipping address",
        "spending cap",
        "primary approval",
        "gift consent",
        "store policy",
        "aggregated order",
    ],
    "naturalization_focus": (
        "Keep each owner ecosystem meaningful. Agents must consult their "
        "owned files and personal SQLite databases before requesting, "
        "approving, or committing any retail action. Do not collapse the "
        "task to a single buyer + single seller."
    ),
}

__all__ = [
    "SharedAccountLoader",
    "load_shared_account_scenario",
    "materialize_shared_account_bundle",
    "CrossAccountLoader",
    "CrossAccountScenarioBundle",
    "load_cross_account_scenario",
    "materialize_cross_account_bundle",
    "StoreRepDyadLoader",
    "StoreRepDyadScenarioBundle",
    "load_store_rep_dyad_scenario",
    "materialize_store_rep_dyad_bundle",
    "HubAggregatorLoader",
    "HubAggregatorScenarioBundle",
    "load_hub_aggregator_scenario",
    "Tau2RetailLoader",  # compatibility alias
    "load_household_exchange_scenario",  # compatibility alias
    "materialize_household_bundle",  # compatibility alias
    "NATURALIZATION_HINTS",
]
