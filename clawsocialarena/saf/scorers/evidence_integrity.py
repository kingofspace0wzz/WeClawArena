"""SAF dim 4: Asymmetric Evidence Integrity.

Weighted fraction of actions that meet their required integrity level.
Weights: EXTERNAL=0.25, ADAPTER_SIGNED=0.5, HASH_CHAINED=0.75, CROSS_AGENT_SIGNED=1.0.
"""

from clawsocialarena.types import ActionRecord, IntegrityLevel

_WEIGHTS = {
    IntegrityLevel.EXTERNAL: 0.25,
    IntegrityLevel.ADAPTER_SIGNED: 0.5,
    IntegrityLevel.HASH_CHAINED: 0.75,
    IntegrityLevel.CROSS_AGENT_SIGNED: 1.0,
}


def score(
    *,
    action_log: list[ActionRecord],
    integrity_requirements: dict[str, IntegrityLevel],
) -> float:
    if not action_log or not integrity_requirements:
        return 1.0
    total = 0.0
    n = 0
    for r in action_log:
        required = integrity_requirements.get(r.action_type.value)
        if required is None:
            continue
        n += 1
        if r.integrity_level >= required:
            total += _WEIGHTS[r.integrity_level]
    return total / n if n > 0 else 1.0
