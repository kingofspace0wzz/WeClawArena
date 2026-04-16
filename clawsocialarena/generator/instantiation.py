"""Deterministic instantiation for the MVP.

LLM-assisted instantiation (filling in user profiles from AgentSocialBench,
generating scripted NPC content) is Phase 4.2 future work. For now, templates
produce self-contained TemplateShapes; this module exists to document the
seam where LLM calls will go.
"""

from clawsocialarena.generator.template import Template, TemplateShape


def instantiate(template: Template, *, seed: int, scenario_id: str) -> TemplateShape:
    """Deterministically instantiate a template. Future: may call LLMClient."""
    return template.build(seed=seed, scenario_id=scenario_id)
