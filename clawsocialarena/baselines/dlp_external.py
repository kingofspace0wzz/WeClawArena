"""Rule-based DLP sanitizer — external comparison baseline.

Per spec §5.2 item 2, a rule-based DLP (Data Loss Prevention)
post-message filter is one of the three external baselines. It mirrors
enterprise-grade DLP products: regex and keyword checks against every
outbound message, with verdicts limited to ``allow``, ``rewrite``
(redact matching substrings), or ``block``. Critically it is NOT
MSWM-aware — it sees each message in isolation and cannot catch
inferential leakage across messages.

The baseline is packaged as a :class:`~clawsocialarena.protocols.policy_hook.PolicyHook`
so it can be plugged into :class:`~clawsocialarena.gateway.session.Session`
directly. The :func:`build_dlp_session` helper is a thin wrapper that
constructs a Session pre-wired with the DLP hook; tests and batch
runs use it to drive DLP-audited gateway sessions end-to-end.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from clawsocialarena.gateway.session import Session
from clawsocialarena.protocols.policy_hook import (
    PolicyDecision,
    PolicyVerdict,
)
from clawsocialarena.types import ActionRecord, AuditCondition


@dataclass
class DlpRule:
    """One DLP rule: a regex pattern plus a verdict policy.

    Attributes:
        rule_id: stable identifier. Reported on the emitted PolicyDecision.
        pattern: compiled regex used against ``payload["content"]``.
        verdict: one of ``"block"``, ``"rewrite"``, or ``"flag"``. ``flag``
            reports the match without mutating content (allow + reason).
        replacement: substitution string for ``rewrite`` verdicts;
            defaults to ``[REDACTED]``. Ignored for ``block`` / ``flag``.
        reason: human-readable explanation; surfaces on the policy
            decision.
    """

    rule_id: str
    pattern: re.Pattern[str]
    verdict: str = "rewrite"
    replacement: str = "[REDACTED]"
    reason: str = ""


@dataclass
class RuleBasedDLP:
    """PolicyHook that runs a list of DLP rules against outbound content.

    The hook kind is ``message`` so the gateway only fires it on
    OUTBOUND_MESSAGE records. Tool calls and memory writes are out of
    scope: enterprise DLP typically filters egress traffic, not
    internal agent state.

    Rules fire in the supplied order; the FIRST match wins. ``block``
    short-circuits the remaining rules; ``rewrite`` redacts the matched
    span and keeps evaluating (subsequent rules see the already-redacted
    text). ``flag`` emits the policy decision without mutating content.
    """

    hook_kind = "message"

    rules: list[DlpRule] = field(default_factory=list)

    def evaluate(
        self, *, action: ActionRecord, context: dict
    ) -> PolicyDecision:
        content = str(action.payload.get("content", ""))
        rewritten = content
        matched_rule: DlpRule | None = None
        for rule in self.rules:
            if rule.pattern.search(rewritten) is None:
                continue
            if rule.verdict == "block":
                return PolicyDecision(
                    verdict=PolicyVerdict.BLOCK,
                    reason=rule.reason or f"DLP {rule.rule_id} blocked",
                    policy_id=rule.rule_id,
                )
            if rule.verdict == "rewrite":
                rewritten = rule.pattern.sub(rule.replacement, rewritten)
                matched_rule = rule
                continue
            if rule.verdict == "flag":
                # Flag: allow but report.
                return PolicyDecision(
                    verdict=PolicyVerdict.ALLOW,
                    reason=rule.reason or f"DLP {rule.rule_id} matched",
                    policy_id=rule.rule_id,
                )

        if matched_rule is not None and rewritten != content:
            return PolicyDecision(
                verdict=PolicyVerdict.REWRITE,
                rewritten_content=rewritten,
                reason=matched_rule.reason
                or f"DLP {matched_rule.rule_id} redacted",
                policy_id=matched_rule.rule_id,
            )
        return PolicyDecision(verdict=PolicyVerdict.ALLOW)


def _default_ruleset() -> list[DlpRule]:
    """Compact demo ruleset: SSN-like, credit-card-like, email-like.

    Enterprise DLPs ship with hundreds of rules; this default is just
    enough for a test harness. Real deployments swap in their own list
    via :func:`build_dlp_session`.
    """

    return [
        DlpRule(
            rule_id="dlp.ssn",
            pattern=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
            verdict="rewrite",
            reason="SSN-like pattern",
        ),
        DlpRule(
            rule_id="dlp.credit-card",
            pattern=re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),
            verdict="rewrite",
            reason="credit-card-like pattern",
        ),
        DlpRule(
            rule_id="dlp.email",
            pattern=re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
            verdict="flag",
            reason="email address",
        ),
    ]


def build_dlp_session(
    *,
    scenario_id: str,
    db_path: Path | str,
    work_dir: Path | str | None = None,
    phase_schedule: list[dict] | None = None,
    rules: Iterable[DlpRule] | None = None,
    condition: AuditCondition = AuditCondition.ENFORCE,
) -> Session:
    """Return a Session pre-wired with the DLP hook.

    The gateway hook chain becomes ``[RuleBasedDLP]``; additional hooks
    can be appended to the returned Session's ``hooks`` list if the
    caller needs a layered policy stack.

    ``condition`` defaults to ENFORCE so the DLP baseline actually
    rewrites/blocks content; under PASSIVE the hook's decisions are
    logged via POLICY_DECISION rows but the outbound content is not
    modified.
    """

    ruleset = list(rules) if rules is not None else _default_ruleset()
    dlp_hook = RuleBasedDLP(rules=ruleset)
    return Session.build(
        scenario_id=scenario_id,
        condition=condition,
        db_path=db_path,
        work_dir=work_dir,
        phase_schedule=phase_schedule,
        hooks=[dlp_hook],
    )
