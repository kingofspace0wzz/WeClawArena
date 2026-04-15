"""Decorator MessageBus that appends action records and (as of Phase 3) runs
PolicyHooks under three conditions (baseline / passive / enforce)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.phase_tracker import PhaseTracker
from clawsocialarena.protocols import MessageBus
from clawsocialarena.protocols.policy_hook import (
    PolicyDecision,
    PolicyHook,
    PolicyVerdict,
)
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    AuditCondition,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


class AuditedMessageBus:
    def __init__(
        self,
        *,
        inner: MessageBus,
        action_log: ActionLog,
        condition: AuditCondition = AuditCondition.BASELINE,
        phase_tracker: PhaseTracker | None = None,
        shadow_log: ActionLog | None = None,
        hooks: list[PolicyHook] | None = None,
    ) -> None:
        self._inner = inner
        self._log = action_log
        self._condition = condition
        self._tracker = phase_tracker
        self._shadow = shadow_log
        self._hooks = list(hooks) if hooks else []

    async def send(self, *, sender_id: str, recipient_id: str, content: str) -> str:
        social_phase = (
            self._tracker.current_phase() if self._tracker is not None else SocialPhase.DISCOVERY
        )

        # Build a provisional record so hooks can evaluate realistic content.
        provisional = ActionRecord(
            action_id=f"act-{uuid.uuid4().hex[:12]}",
            prev_hash=self._log.head_hash(sender_id),
            agent_id=sender_id,
            action_type=ActionType.OUTBOUND_MESSAGE,
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=social_phase,
            payload={"recipient_id": recipient_id, "content": content},
            integrity_level=IntegrityLevel.HASH_CHAINED,
        )

        content_to_send = content
        blocked = False

        if self._condition != AuditCondition.BASELINE and self._hooks:
            for hook in self._hooks:
                decision: PolicyDecision = hook.evaluate(
                    action=provisional, context={}
                )
                # Log the policy_decision regardless of verdict
                self._append_policy_decision(sender_id, decision)

                if self._condition == AuditCondition.ENFORCE:
                    if decision.verdict == PolicyVerdict.BLOCK:
                        blocked = True
                        break
                    if decision.verdict == PolicyVerdict.REWRITE and decision.rewritten_content is not None:
                        content_to_send = decision.rewritten_content
                        # Continue with further hooks (they may further rewrite)

        if blocked:
            # Swallow the outbound entirely (no log, no delivery)
            return ""

        # Rebuild the outbound record if content was rewritten (so the logged
        # payload matches what gets delivered)
        if content_to_send != content:
            outbound_rec = provisional.model_copy(
                update={
                    "prev_hash": self._log.head_hash(sender_id),  # refresh head after policy_decision logs
                    "payload": {"recipient_id": recipient_id, "content": content_to_send},
                }
            )
        else:
            outbound_rec = provisional.model_copy(
                update={"prev_hash": self._log.head_hash(sender_id)}
            )
        self._log.append(outbound_rec)

        if self._shadow is not None:
            shadow_rec = outbound_rec.model_copy(
                update={"prev_hash": self._shadow.head_hash(sender_id)}
            )
            self._shadow.append(shadow_rec)

        return await self._inner.send(
            sender_id=sender_id, recipient_id=recipient_id, content=content_to_send
        )

    async def recv(self, *, recipient_id: str) -> tuple[str, str] | None:
        return await self._inner.recv(recipient_id=recipient_id)

    async def record_tool_call(
        self, *, agent_id: str, tool_name: str, arguments: dict
    ) -> str:
        """Append a TOOL_CALL record to primary + shadow logs.

        Condition-gated: baseline skips hooks entirely; passive/enforce evaluate
        tool-kind hooks (``hook_kind == "tool"``) and may rewrite/block under
        enforce. Returns the logged ``action_id`` so the caller can link a
        matching TOOL_OBSERVATION_RETURN to it.
        """
        social_phase = (
            self._tracker.current_phase()
            if self._tracker is not None
            else SocialPhase.DISCOVERY
        )
        rec = ActionRecord(
            action_id=f"tc-{uuid.uuid4().hex[:12]}",
            prev_hash=self._log.head_hash(agent_id),
            agent_id=agent_id,
            action_type=ActionType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=social_phase,
            payload={"tool_name": tool_name, "arguments": arguments},
            integrity_level=IntegrityLevel.HASH_CHAINED,
        )

        if self._condition != AuditCondition.BASELINE and self._hooks:
            for hook in self._hooks:
                if getattr(hook, "hook_kind", "message") != "tool":
                    continue
                decision: PolicyDecision = hook.evaluate(action=rec, context={})
                self._append_policy_decision(agent_id, decision)
                if (
                    self._condition == AuditCondition.ENFORCE
                    and decision.verdict == PolicyVerdict.BLOCK
                ):
                    # Blocked: skip the TOOL_CALL log entirely; caller treats as no-op.
                    return ""

        # Refresh prev_hash since policy_decision writes (if any) moved the head.
        rec = rec.model_copy(update={"prev_hash": self._log.head_hash(agent_id)})
        self._log.append(rec)
        if self._shadow is not None:
            shadow_rec = rec.model_copy(
                update={"prev_hash": self._shadow.head_hash(agent_id)}
            )
            self._shadow.append(shadow_rec)
        return rec.action_id

    async def record_tool_observation(
        self,
        *,
        agent_id: str,
        tool_call_action_id: str,
        tool_name: str,
        observation: str,
    ) -> str:
        """Append a TOOL_OBSERVATION_RETURN record linked to the TOOL_CALL via
        ``payload["tool_call_action_id"]``. Primary + shadow logs."""
        social_phase = (
            self._tracker.current_phase()
            if self._tracker is not None
            else SocialPhase.DISCOVERY
        )
        rec = ActionRecord(
            action_id=f"tr-{uuid.uuid4().hex[:12]}",
            prev_hash=self._log.head_hash(agent_id),
            agent_id=agent_id,
            action_type=ActionType.TOOL_OBSERVATION_RETURN,
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=social_phase,
            payload={
                "tool_call_action_id": tool_call_action_id,
                "tool_name": tool_name,
                "observation": observation,
            },
            integrity_level=IntegrityLevel.HASH_CHAINED,
        )
        self._log.append(rec)
        if self._shadow is not None:
            shadow_rec = rec.model_copy(
                update={"prev_hash": self._shadow.head_hash(agent_id)}
            )
            self._shadow.append(shadow_rec)
        return rec.action_id

    def _append_policy_decision(self, agent_id: str, decision: PolicyDecision) -> None:
        """Append a POLICY_DECISION action record capturing the hook's verdict."""
        rec = ActionRecord(
            action_id=f"pol-{uuid.uuid4().hex[:12]}",
            prev_hash=self._log.head_hash(agent_id),
            agent_id=agent_id,
            action_type=ActionType.POLICY_DECISION,
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=(
                self._tracker.current_phase() if self._tracker is not None else SocialPhase.DISCOVERY
            ),
            payload={
                "verdict": decision.verdict.value,
                "policy_id": decision.policy_id,
                "reason": decision.reason,
            },
            integrity_level=IntegrityLevel.HASH_CHAINED,
        )
        self._log.append(rec)
        if self._shadow is not None:
            shadow_rec = rec.model_copy(
                update={"prev_hash": self._shadow.head_hash(agent_id)}
            )
            self._shadow.append(shadow_rec)
