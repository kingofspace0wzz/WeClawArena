"""Per-archetype loaders for the tau2_retail family pack.

Each archetype (shared_account, cross_account, store_rep_dyad,
hub_aggregator) ships its own loader module. The package-level
__init__ exposes the four entry-point functions so external callers
(family_pack_registry, tests) can import without knowing the
submodule layout.
"""
from clawsocialarena.generator.family_packs.tau2_retail.loaders.loader_shared_account import (
    SharedAccountLoader,
    load_shared_account_scenario,
)
from clawsocialarena.generator.family_packs.tau2_retail.loaders.loader_cross_account import (
    CrossAccountLoader,
    CrossAccountScenarioBundle,
    load_cross_account_scenario,
)

__all__ = [
    "SharedAccountLoader",
    "load_shared_account_scenario",
    "CrossAccountLoader",
    "CrossAccountScenarioBundle",
    "load_cross_account_scenario",
]
