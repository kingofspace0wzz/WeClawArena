"""Decorator MessageBus that appends action records and (as of Phase 3) runs
PolicyHooks under three conditions (baseline / passive / enforce).

As of Task 3.5e: under ENFORCE, message-kind hooks compose — each hook
evaluates the CURRENT (post-previous-rewrite) content rather than the
original provisional. The outbound's ``action_id`` is also stable: it is
minted once up front and reused for the (possibly-rewritten) final
OUTBOUND_MESSAGE record, so every POLICY_DECISION.payload carries a
``target_action_id`` that links back to the outbound this decision is about
(even when that outbound is subsequently blocked). The payload also carries
``original_content`` and ``post_content`` so the evidence survives a block.
"""

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

    async def send(
        self,
        *,
        sender_id: str,
        recipient_id: str,
        content: str,
        source_action_ids: list[str] | None = None,
    ) -> str:
        social_phase = (
            self._tracker.current_phase() if self._tracker is not None else SocialPhase.DISCOVERY
        )

        # Mint a stable action_id for the outbound UP FRONT. This same id is
        # reused whether or not hooks rewrite the content, and is recorded as
        # ``target_action_id`` on every related POLICY_DECISION — so even when
        # the outbound is blocked (no OUTBOUND_MESSAGE row), the policy rows
        # still point at the action they were evaluating.
        outbound_action_id = f"act-{uuid.uuid4().hex[:12]}"
        original_content = content
        current_content = content
        blocked = False

        if self._condition != AuditCondition.BASELINE and self._hooks:
            for hook in self._hooks:
                if getattr(hook, "hook_kind", "message") != "message":
                    continue
                # Rebuild the provisional with CURRENT content each iteration
                # so hook N sees the result of hook N-1's rewrite (under
                # ENFORCE). Under PASSIVE we do NOT mutate current_content, so
                # each hook sees the original — preserving passive semantics.
                provisional = ActionRecord(
                    action_id=outbound_action_id,
                    prev_hash=self._log.head_hash(sender_id),
                    agent_id=sender_id,
                    action_type=ActionType.OUTBOUND_MESSAGE,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    execution_phase=ExecutionPhase.NOMINAL,
                    social_phase=social_phase,
                    payload={"recipient_id": recipient_id, "content": current_content},
                    integrity_level=IntegrityLevel.HASH_CHAINED,
                    source_action_ids=list(source_action_ids or []),
                )
                decision: PolicyDecision = hook.evaluate(action=provisional, context={})
                post_content = (
                    decision.rewritten_content
                    if decision.verdict == PolicyVerdict.REWRITE
                    else None
                )
                self._append_policy_decision(
                    agent_id=sender_id,
                    decision=decision,
                    target_action_id=outbound_action_id,
                    original_content=original_content,
                    post_content=post_content,
                )

                if self._condition == AuditCondition.ENFORCE:
                    if decision.verdict == PolicyVerdict.BLOCK:
                        blocked = True
                        break
                    if (
                        decision.verdict == PolicyVerdict.REWRITE
                        and decision.rewritten_content is not None
                    ):
                        current_content = decision.rewritten_content

        if blocked:
            # Swallow the outbound entirely (no log, no delivery)
            return ""

        # Final OUTBOUND_MESSAGE: appended ONCE with the stable action_id and
        # the final (possibly composed-rewritten) content. Refresh prev_hash
        # since any policy_decision writes above moved the head.
        outbound_rec = ActionRecord(
            action_id=outbound_action_id,
            prev_hash=self._log.head_hash(sender_id),
            agent_id=sender_id,
            action_type=ActionType.OUTBOUND_MESSAGE,
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=social_phase,
            payload={"recipient_id": recipient_id, "content": current_content},
            integrity_level=IntegrityLevel.HASH_CHAINED,
            source_action_ids=list(source_action_ids or []),
        )
        self._log.append(outbound_rec)

        if self._shadow is not None:
            shadow_rec = outbound_rec.model_copy(
                update={"prev_hash": self._shadow.head_hash(sender_id)}
            )
            self._shadow.append(shadow_rec)

        return await self._inner.send(
            sender_id=sender_id, recipient_id=recipient_id, content=current_content
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

        As of Task 3.5e: every POLICY_DECISION emitted here carries
        ``target_action_id`` = the tool_call's stable action_id (minted up
        front), plus ``original_content`` / ``post_content`` using the tool
        arguments as the evidence blob.
        """
        social_phase = (
            self._tracker.current_phase()
            if self._tracker is not None
            else SocialPhase.DISCOVERY
        )

        tool_call_action_id = f"tc-{uuid.uuid4().hex[:12]}"
        blocked = False

        if self._condition != AuditCondition.BASELINE and self._hooks:
            for hook in self._hooks:
                if getattr(hook, "hook_kind", "message") != "tool":
                    continue
                # Rebuild the provisional each loop so a future tool-rewrite
                # hook chain would compose. Today the bus doesn't act on
                # tool-rewrite (no tool-rewrite semantics defined), but the
                # policy_decision payload still captures the decision + target.
                provisional = ActionRecord(
                    action_id=tool_call_action_id,
                    prev_hash=self._log.head_hash(agent_id),
                    agent_id=agent_id,
                    action_type=ActionType.TOOL_CALL,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    execution_phase=ExecutionPhase.NOMINAL,
                    social_phase=social_phase,
                    payload={"tool_name": tool_name, "arguments": arguments},
                    integrity_level=IntegrityLevel.HASH_CHAINED,
                )
                decision: PolicyDecision = hook.evaluate(action=provisional, context={})
                post_content = (
                    decision.rewritten_content
                    if decision.verdict == PolicyVerdict.REWRITE
                    else None
                )
                # Use a compact string rendering of the tool call as
                # original_content so blocked tool-call evidence survives.
                original_content = f"{tool_name}({arguments!r})"
                self._append_policy_decision(
                    agent_id=agent_id,
                    decision=decision,
                    target_action_id=tool_call_action_id,
                    original_content=original_content,
                    post_content=post_content,
                )
                if (
                    self._condition == AuditCondition.ENFORCE
                    and decision.verdict == PolicyVerdict.BLOCK
                ):
                    blocked = True
                    break

        if blocked:
            # Swallow the TOOL_CALL entirely; caller treats as no-op.
            return ""

        # Emit the TOOL_CALL with the stable action_id and a refreshed prev_hash.
        rec = ActionRecord(
            action_id=tool_call_action_id,
            prev_hash=self._log.head_hash(agent_id),
            agent_id=agent_id,
            action_type=ActionType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=social_phase,
            payload={"tool_name": tool_name, "arguments": arguments},
            integrity_level=IntegrityLevel.HASH_CHAINED,
        )
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

    def _append_policy_decision(
        self,
        *,
        agent_id: str,
        decision: PolicyDecision,
        target_action_id: str,
        original_content: str | None = None,
        post_content: str | None = None,
    ) -> None:
        """Append a POLICY_DECISION action record capturing the hook's verdict.

        ``target_action_id`` identifies the outbound/tool_call this decision
        is about, even when that action is ultimately blocked (no row) or
        rewritten. ``original_content`` and ``post_content`` preserve the
        evidence blob independently of the outbound row's payload — so a
        blocked message's content is still auditable from the POLICY_DECISION
        alone.
        """
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
                "target_action_id": target_action_id,
                "original_content": original_content,
                "post_content": post_content,
            },
            integrity_level=IntegrityLevel.HASH_CHAINED,
        )
        self._log.append(rec)
        if self._shadow is not None:
            shadow_rec = rec.model_copy(
                update={"prev_hash": self._shadow.head_hash(agent_id)}
            )
            self._shadow.append(shadow_rec)
