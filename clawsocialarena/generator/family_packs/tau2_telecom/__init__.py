"""Tau2 telecom family pack.

Source: ``knowledge/tau2-bench/data/tau2/domains/telecom/``. The single-
user telecom flow is reframed as a family-plan account with a primary
account holder plus one secondary line owner; the family pack produces
a v2 scenario with a two-node agent_graph and coordination_mode=graph.

See ``docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md``
section 4.5 for the full design.
"""

from clawsocialarena.generator.family_packs.tau2_telecom.loader import (
    Tau2TelecomLoader,
    load_family_plan_roaming_scenario,
)
from clawsocialarena.generator.family_packs.tau2_telecom.materialize import (
    materialize_family_plan_bundle,
)


NATURALIZATION_HINTS: dict[str, object] = {
    "domain": "wireless carrier customer support",
    "tone": "telecom service assistant, troubleshoot-then-resolve, careful about account scope",
    "key_terms": [
        "family-plan account",
        "primary account holder",
        "secondary line owner",
        "roaming",
        "billing dispute",
        "service incident",
        "line owner consent",
    ],
    "naturalization_focus": (
        "Make plans, devices, and billing artifacts feel like real "
        "wireless-carrier records. The per-line authorization rule (only "
        "the line owner may consent to changes touching their line; only "
        "the primary holder may commit account-wide changes and dispute "
        "charges) MUST stay visible in the opening message and persona "
        "notes."
    ),
}


__all__ = [
    "Tau2TelecomLoader",
    "load_family_plan_roaming_scenario",
    "materialize_family_plan_bundle",
    "NATURALIZATION_HINTS",
]
