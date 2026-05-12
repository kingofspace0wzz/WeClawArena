"""MARBLE research-collaboration family pack.

Source: ``knowledge/MARBLE/multiagentbench/research/research_main.jsonl``.
The native MARBLE research scenarios put 3-5 agents in a collaboration
graph; this v2 pack caps at 3 PI nodes (one per lab) and reframes the
multi-agent proposal task with explicit citation-authorization rules.

See ``docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md``
section 4.1 for the full design.
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
