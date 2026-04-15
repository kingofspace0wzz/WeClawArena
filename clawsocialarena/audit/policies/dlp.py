"""Rule-based DLP sanitizer (minimum viable).

This is the external comparison baseline for §5.2 ("prompt-only L0-L4 ladder
/ rule-based DLP sanitizer / vanilla-AA post-hoc auditor"). A more complete
DLP rule set is authored in Phase 5.
"""

from __future__ import annotations

import re

from clawsocialarena.protocols.policy_hook import (
    PolicyDecision,
    PolicyVerdict,
)
from clawsocialarena.types import ActionRecord


class RuleBasedDLP:
    """Forbidden-phrase matcher with naive redaction."""

    def __init__(self, *, forbidden_phrases: list[str], policy_id: str = "dlp-rule") -> None:
        self._forbidden = [re.compile(re.escape(p), re.IGNORECASE) for p in forbidden_phrases]
        self._policy_id = policy_id

    def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
        content = str(action.payload.get("content", ""))
        redacted = content
        matched = False
        for pat in self._forbidden:
            if pat.search(redacted):
                matched = True
                redacted = pat.sub("[redacted]", redacted)
        if matched:
            return PolicyDecision(
                verdict=PolicyVerdict.REWRITE,
                rewritten_content=redacted,
                reason="DLP forbidden phrase match",
                policy_id=self._policy_id,
            )
        return PolicyDecision(verdict=PolicyVerdict.ALLOW)
