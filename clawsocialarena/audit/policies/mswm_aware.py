"""MSWM-aware policy hook (Phase C / Task C6).

Evaluates a configured list of joint-decidability invariants against the
live MSWM state attached to the Session. For each invariant that the MSWM
reports as ``violated`` given the current action, the hook returns a
``PolicyDecision`` with verdict ``block`` (or ``rewrite`` when the invariant
explicitly asks for redaction).

The hook belongs to the ``message`` kind — spec §2.6 says MSWM updates fire
on outbound disclosures and the MSWM-aware containment vignette (§3.1 #1)
catches the inferential-leakage case at send time. Extending the hook to
tool-kind or memory-kind buckets is future work.

Context assumption: ``context["mswm"]`` must be present — the gateway
Session passes it in ``_record_action`` as of Phase C / Task C5.
"""

from __future__ import annotations

from typing import Any

from clawsocialarena.protocols.policy_hook import (
    PolicyDecision,
    PolicyVerdict,
)
from clawsocialarena.types import ActionRecord


class MswmAwareHook:
    """Policy hook that consults :class:`~clawsocialarena.audit.mswm.MSWM`.

    Invariants are plain dicts (the predicate schema documented on
    :meth:`MSWM.joint_decidability`). Each invariant may also carry:

    - ``invariant_id`` — string identifier used as ``policy_id`` on the
      emitted :class:`PolicyDecision`.
    - ``action`` — one of ``"block"`` or ``"rewrite"`` (default ``"block"``).
      For ``"rewrite"``, the hook redacts any item in the current action's
      ``payload["mentioned_items"]`` that overlaps ``forbidden_inference``
      by removing it from the list; ``rewritten_content`` copies the
      textual content unchanged (the mentioned_items list is the
      load-bearing state for MSWM).

    Hook kind is ``message``; the Session dispatch table already routes
    outbound_message events to message-kind hooks.
    """

    hook_kind = "message"

    def __init__(self, invariants: list[dict[str, Any]]) -> None:
        self._invariants = list(invariants)

    def evaluate(
        self, *, action: ActionRecord, context: dict
    ) -> PolicyDecision:
        mswm = context.get("mswm")
        if mswm is None:
            # No MSWM in the context — the hook is a no-op. This path keeps
            # the hook safe against mis-plumbing (e.g. a legacy caller
            # invoking the hook directly without MSWM).
            return PolicyDecision(verdict=PolicyVerdict.ALLOW)

        for inv in self._invariants:
            for_agent = inv.get("for_agent")
            if not for_agent:
                # Default the subject to the outbound's recipient: most
                # inferential-leakage invariants are scoped to the party
                # who could form the inference upon receiving the current
                # message. If the payload carries no recipient, skip.
                for_agent = action.payload.get("recipient_id")
                if not for_agent:
                    continue
                inv = {**inv, "for_agent": for_agent}

            verdict = mswm.joint_decidability(action.agent_id, inv)
            if verdict != "violated":
                continue

            policy_id = inv.get("invariant_id") or "mswm-invariant"
            reason = inv.get(
                "reason",
                f"MSWM joint decidability violated for agent={for_agent}",
            )
            mode = inv.get("action", "block")
            if mode == "rewrite":
                rewritten = self._redact(action, inv)
                rewritten_items = self._rewrite_mentioned_items(action, inv)
                return PolicyDecision(
                    verdict=PolicyVerdict.REWRITE,
                    rewritten_content=rewritten,
                    rewritten_mentioned_items=rewritten_items,
                    reason=reason,
                    policy_id=policy_id,
                )
            return PolicyDecision(
                verdict=PolicyVerdict.BLOCK,
                reason=reason,
                policy_id=policy_id,
            )

        return PolicyDecision(verdict=PolicyVerdict.ALLOW)

    @staticmethod
    def _redact(action: ActionRecord, invariant: dict[str, Any]) -> str:
        """Return a textual replacement for the outbound content.

        The hook signals which items were redacted via
        ``rewritten_mentioned_items`` on the :class:`PolicyDecision`; the
        text itself gets a sentinel marker appended so human readers of
        cassettes can see the redaction occurred.
        """

        content = str(action.payload.get("content", ""))
        forbidden = invariant.get("forbidden_inference") or []
        marker = f" [redacted items referencing {', '.join(forbidden)}]"
        return content + marker

    @staticmethod
    def _rewrite_mentioned_items(
        action: ActionRecord, invariant: dict[str, Any]
    ) -> list[str]:
        """Drop every forbidden item from ``payload.mentioned_items``.

        Any item listed in the invariant's ``forbidden_inference`` is
        considered the trigger; filtering it out makes the post-rewrite
        payload consistent with the MSWM update that the Session must
        re-apply after the hook returns.
        """

        mentioned = action.payload.get("mentioned_items") or []
        forbidden = set(invariant.get("forbidden_inference") or [])
        return [item for item in mentioned if item not in forbidden]
