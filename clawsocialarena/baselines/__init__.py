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

from clawsocialarena.baselines.prompt_ladder import (
    PrivacyLevel,
    level_prefix,
    system_prompt_with_level,
)
from clawsocialarena.baselines.vanilla_aa import (
    VanillaAAEvalRunner,
    VanillaAAScorecard,
)

__all__ = [
    "PrivacyLevel",
    "level_prefix",
    "system_prompt_with_level",
    "VanillaAAEvalRunner",
    "VanillaAAScorecard",
]
