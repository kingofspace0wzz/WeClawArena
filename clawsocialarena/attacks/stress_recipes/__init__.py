"""Stress attack recipes for ClawSocialArena v2 spec Section 4.

Each recipe in this package implements the :class:`StressRecipe`
protocol declared in :mod:`base`. Recipes are registered in
:data:`STRESS_RECIPE_REGISTRY` keyed by the canonical recipe name.

The four canonical stress recipes per spec Section 4.2 are:

    security      -> indirect_resource_prompt_injection
    privacy       -> adaptive_exfiltration
    governance    -> poisoned_consent_row (fake_approval_chain)
    collaboration -> adaptive_malicious_peer

Static stress recipes mutate the variant bundle on disk before
runtime; the live executor reads the mutated resources via normal MCP
tool dispatch and the attack lands without any new runtime substrate.
Some generic adaptive recipes still declare ``requires_runtime_peer``
and supply an ``attacker_peer_prompt``. Family-specific owned-resource
playbooks, such as bargaining, bidding, and workspace, prefer static
scenario/resource overlays so the docker runner does not need
family-specific delivery branches.

Wiring: the orchestrator selects the recipe by looking up
``variant_metadata.attack_recipe`` against :data:`STRESS_RECIPE_REGISTRY`.
Recipes that are absent from the registry fall back to the legacy
single-shot ``opening_message`` injection (the standard attacks).
"""
from __future__ import annotations

from clawsocialarena.attacks.stress_recipes.base import (
    StressRecipe,
    StressVariantArtifacts,
)

# Recipe modules register themselves into this dict at import time
# via the module-level ``register_recipe`` call. Importing the package
# imports all four canonical recipes so the registry is fully
# populated by the time the orchestrator consults it.
STRESS_RECIPE_REGISTRY: dict[str, StressRecipe] = {}


def register_recipe(recipe: StressRecipe) -> None:
    """Register a stress recipe in the global registry by its name.

    Idempotent: re-registering the same name overwrites the prior
    entry (useful for tests that swap in a stub recipe).
    """
    STRESS_RECIPE_REGISTRY[recipe.name] = recipe


# Import recipe modules so they register themselves. Each module
# defines its recipe and calls ``register_recipe`` at module scope.
from clawsocialarena.attacks.stress_recipes import (  # noqa: E402,F401
    security_indirect_resource_injection,
    privacy_adaptive_exfiltration,
    governance_poisoned_consent,
    collaboration_adaptive_peer,
    bargaining_mode_local_playbooks,
    bidding_mode_local_playbooks,
    workspace_mode_local_playbooks,
    travel_mode_local_playbooks,
)


__all__ = [
    "STRESS_RECIPE_REGISTRY",
    "StressRecipe",
    "StressVariantArtifacts",
    "register_recipe",
]
