"""External comparison baselines (spec §5.2).

This sub-package bundles the three non-SAF baselines against which SAF is
measured in the main experiments:

1. Prompt-only L0-L4 ladder — what prompt-level defense alone achieves with
   no runtime hooks, no policy engine, and no audit layer.
2. Rule-based DLP sanitizer — implemented as a policy hook (see
   ``clawsocialarena.audit.policies.dlp``); listed here for reference only.
3. Vanilla Auditable Agents post-hoc auditor — same inputs as SAF but
   without our social-multi-agent adaptations (no MSWM, no inference-chain
   attribution, no phase-scoped policies).
"""

from clawsocialarena.baselines.dlp_external import (
    DlpRule,
    RuleBasedDLP,
    build_dlp_session,
)
from clawsocialarena.baselines.prompt_ladder import (
    PrivacyLevel,
    apply_ladder_to_prompts,
    level_prefix,
    scenario_variation_bundle,
    system_prompt_with_level,
)
from clawsocialarena.baselines.vanilla_aa import VanillaAAEvalRunner

__all__ = [
    "DlpRule",
    "PrivacyLevel",
    "RuleBasedDLP",
    "VanillaAAEvalRunner",
    "apply_ladder_to_prompts",
    "build_dlp_session",
    "level_prefix",
    "scenario_variation_bundle",
    "system_prompt_with_level",
]
