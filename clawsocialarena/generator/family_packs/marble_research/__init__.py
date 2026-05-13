"""MARBLE research-collaboration family pack.

Eight tasks across three MARBLE-seeded research domains (interdisciplinary_tech,
cybersec_ml, rl_snn). Each task has 3, 4, or 5 participating PIs drawn from
seed-specific researcher pools. Profiles, lab names, and unpublished results
come from ``marble_seed_data.ALL_TASKS`` and ``marble_seed_data.ALL_SEEDS``.

The multi-agent proposal task enforces explicit citation-authorization rules
and requires the convener PI to obtain approval before citing any other PI's
unpublished result.

See ``docs/superpowers/specs/2026-05-13-marble-task-diversity-redesign.md``
for the full design.
"""

from clawsocialarena.generator.family_packs.marble_research.loader import (
    MarbleResearchLoader,
    load_research_collaboration_scenario,
)
from clawsocialarena.generator.family_packs.marble_research.materialize import (
    materialize_research_collaboration_bundle,
)


NATURALIZATION_HINTS: dict[str, object] = {
    "domain": "academic research collaboration",
    "tone": "PI-to-PI professional discourse, careful about authorship and IP",
    "key_terms": [
        "principal investigator",
        "5Q proposal",
        "problem statement",
        "research gap",
        "unpublished result",
        "citation approval",
        "lab affiliation",
    ],
    "naturalization_focus": (
        "Make the seed paper, lab profiles, and proposed contributions "
        "feel like real ML / systems research. The authorization rule "
        "(citing a PI's unpublished result requires their explicit "
        "grant_citation_approval; only the convener PI can finalize the "
        "proposal) MUST stay visible -- preserve the 5Q completeness "
        "requirement (problem, importance, difficulty, gap, approach)."
    ),
}


__all__ = [
    "MarbleResearchLoader",
    "load_research_collaboration_scenario",
    "materialize_research_collaboration_bundle",
    "NATURALIZATION_HINTS",
]
