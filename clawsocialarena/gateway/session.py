"""Per-scenario Session object for the gateway.

A :class:`Session` holds the audit substrate (``ActionLog``, ``ShadowLog``,
``PhaseTracker``), the optional cassette recorder, and any registered
``PolicyHook`` instances for a single scenario run. It is the gateway-layer
counterpart to the v1 ``ScenarioRunner``'s construction block (see
``clawsocialarena/runtime/runner.py`` lines 41-85) stripped of the agent
registry: the gateway wires agents out-of-process, so ``Session`` is a pure
data-plus-construction object.

Under :data:`~clawsocialarena.types.AuditCondition.BASELINE` all substrate
fields are ``None``, mirroring the "deployment without audit infrastructure"
condition in spec §5.1. Under ``PASSIVE`` or ``ENFORCE`` the full set of
audit primitives is instantiated.

Phase A.5 lands the real enforce/passive semantics on this object so the
v1 ``AuditedMessageBus`` becomes redundant: every ``record_*`` helper
double-writes to the shadow log, dispatches any matching ``PolicyHook``,
emits a ``POLICY_DECISION`` record per verdict, and under ``ENFORCE``
returns the rewritten content (or a blocked sentinel) so the caller can
propagate it to the inbox queue and, for tool calls, short-circuit the
MCP dispatch.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.mswm import MSWM
from clawsocialarena.audit.phase_tracker import PhaseTracker
from clawsocialarena.audit.shadow_log import ShadowLog
from clawsocialarena.gateway.cassette import CassetteRecorder
from clawsocialarena.gateway.mcp_host import McpHost
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


# Map action types to the ``hook_kind`` buckets v1 used to scope hook
# dispatch. ``message`` fires on outbound messages, ``tool`` fires on the
# tool_call / tool_observation_return pair, ``memory`` fires on memory
# writes / compressions / summaries. Anything not in this table (e.g.
# ``llm_call``) bypasses hook evaluation entirely.
_HOOK_KIND_FOR_ACTION: dict[ActionType, str] = {
    ActionType.OUTBOUND_MESSAGE: "message",
    ActionType.TOOL_CALL: "tool",
    ActionType.TOOL_OBSERVATION_RETURN: "tool",
    ActionType.MEMORY_WRITE: "memory",
    ActionType.MEMORY_COMPRESSION: "memory",
    ActionType.SUMMARY_WRITE: "memory",
}


@dataclass
class RecordOutcome:
    """Result of a :meth:`Session._record_action` call.

    ``action_id`` is ``None`` under BASELINE (no log, no id) or when the
    final action was blocked by a hook under ENFORCE (no record written).
    ``rewritten_content`` is the content the caller should propagate
    downstream (e.g. onto the recipient inbox queue) under ENFORCE after
    a ``rewrite`` verdict; for ``message`` hooks it is a string, for
    ``memory`` hooks it is the replacement memory text. ``blocked`` is
    True when any ENFORCE hook returned ``block``; the caller must treat
    the action as never having occurred (no inbox put, no MCP dispatch).
    """

    action_id: str | None = None
    rewritten_content: str | None = None
    blocked: bool = False


@dataclass
class Session:
    """Container for one scenario's audit substrate and policy hooks.

    Attributes:
        scenario_id: Stable identifier for the scenario this session serves.
        condition: Audit condition governing which substrate fields are wired.
        action_log: Primary hash-chained action log, or ``None`` under BASELINE.
        shadow_log: Privileged independent copy, or ``None`` under BASELINE.
        phase_tracker: Social-phase tracker, or ``None`` under BASELINE.
        cassette: Optional cassette recorder (Task A5 will populate this).
        hooks: Ordered list of ``PolicyHook`` instances to consult at egress.
        inboxes: Lazily-created per-recipient message queues. Each entry is a
            FIFO of ``(sender_id, content)`` tuples waiting for a ``/recv``.
        mcp_host: In-process MCP tool registry. Present under every audit
            condition (BASELINE too) so scenario setup code has a uniform
            registration surface; BASELINE dispatches still run but are not
            logged.
    """

    scenario_id: str
    condition: AuditCondition
    action_log: ActionLog | None = None
    shadow_log: ShadowLog | None = None
    phase_tracker: PhaseTracker | None = None
    cassette: CassetteRecorder | None = None
    hooks: list[PolicyHook] = field(default_factory=list)
    inboxes: dict[str, asyncio.Queue[tuple[str, str]]] = field(default_factory=dict)
    mcp_host: McpHost = field(default_factory=McpHost)
    # MSWM is cheap in-memory state and is always present, even under
    # BASELINE. Under BASELINE the gateway never calls ``_record_action``
    # (early-return on the baseline gate), so MSWM naturally stays empty;
    # keeping the field always-present makes it safe for the gateway HTTP
    # handlers and the MSWM-aware hook to reference unconditionally.
    mswm: MSWM = field(default_factory=MSWM)

    @classmethod
    def build(
        cls,
        scenario_id: str,
        condition: AuditCondition,
        *,
        db_path: str | Path,
        phase_schedule: list[dict] | None = None,
        work_dir: Path | str | None = None,
        hooks: list[PolicyHook] | None = None,
    ) -> "Session":
        """Construct a Session with substrate wired per ``condition``.

        Under BASELINE every substrate field stays ``None`` and ``db_path``
        is ignored; any supplied ``hooks`` are also dropped because baseline
        is defined as "deployment without audit infrastructure" and hook
        dispatch would contradict that semantics. Under PASSIVE or ENFORCE
        the full audit stack is created, with the shadow log persisted
        alongside the primary log as ``{db_path.stem}.shadow.db`` in the
        same directory. When ``work_dir`` is supplied under a non-baseline
        condition, a :class:`CassetteRecorder` is attached that writes a
        ``cassette.jsonl`` file inside that directory.

        Args:
            scenario_id: Stable identifier for the scenario.
            condition: Audit condition governing substrate wiring.
            db_path: Filesystem path for the primary ``ActionLog`` DB.
                Ignored under BASELINE.
            phase_schedule: Optional phase schedule (as used by
                ``PhaseTracker.from_schedule``). When absent a plain
                :class:`PhaseTracker` is created.
            work_dir: Optional filesystem directory for session artifacts
                such as the cassette. When omitted, no cassette is attached.
                Under BASELINE this argument is ignored.
            hooks: Ordered list of ``PolicyHook`` instances. Ignored under
                BASELINE.
        """

        if condition == AuditCondition.BASELINE:
            return cls(scenario_id=scenario_id, condition=condition)

        primary_path = Path(db_path)
        action_log = ActionLog(db_path=primary_path)
        shadow_path = primary_path.parent / f"{primary_path.stem}.shadow.db"
        shadow_log = ShadowLog(db_path=shadow_path)
        phase_tracker = (
            PhaseTracker.from_schedule(phase_schedule)
            if phase_schedule
            else PhaseTracker()
        )
        cassette: CassetteRecorder | None = None
        if work_dir is not None:
            cassette = CassetteRecorder(Path(work_dir) / "cassette.jsonl")
        return cls(
            scenario_id=scenario_id,
            condition=condition,
            action_log=action_log,
            shadow_log=shadow_log,
            phase_tracker=phase_tracker,
            cassette=cassette,
            hooks=list(hooks) if hooks else [],
        )

    def close(self) -> None:
        """Release per-session resources. Idempotent.

        Currently closes the cassette recorder if one is attached. Future
        resources (open DB handles, MCP hosts) should hook in here too.
        """

        if self.cassette is not None:
            self.cassette.close()

    def ensure_inbox(self, recipient_id: str) -> asyncio.Queue[tuple[str, str]]:
        """Return the inbox queue for ``recipient_id``, creating it on first use.

        Queues are created lazily so the gateway can serve arbitrary recipient
        ids without preconfiguration. The first ``/send`` or ``/recv`` for a
        recipient materializes the queue.
        """

        queue = self.inboxes.get(recipient_id)
        if queue is None:
            queue = asyncio.Queue()
            self.inboxes[recipient_id] = queue
        return queue

    async def record_outbound(
        self,
        *,
        sender_id: str,
        recipient_id: str,
        content: str,
        source_action_ids: list[str] | None = None,
        mentioned_items: list[str] | None = None,
    ) -> RecordOutcome:
        """Append an ``OUTBOUND_MESSAGE`` ActionRecord for a send, if audited.

        Under BASELINE this is a no-op and returns an empty outcome: the
        baseline condition simulates "deployment without audit
        infrastructure" so no log exists to append to and no hooks run.
        Under PASSIVE or ENFORCE the record is appended to the primary
        ``ActionLog`` AND the shadow log, any registered ``message``-kind
        hooks are evaluated, and their verdicts land as ``POLICY_DECISION``
        rows. ENFORCE additionally reflects ``rewrite`` / ``block`` verdicts
        back on the returned :class:`RecordOutcome`:

        - ``rewrite``: ``rewritten_content`` holds the final content; the
          persisted OUTBOUND_MESSAGE row carries this content.
        - ``block``: ``blocked`` is True, ``action_id`` is ``None``, no
          OUTBOUND_MESSAGE row is written (the caller must skip the
          inbox enqueue).

        ``mentioned_items`` is the MSWM payload convention introduced in
        Phase C. When supplied, the items are attached to ``payload`` under
        the ``mentioned_items`` key so ``MSWM.on_action`` can update the
        sender / recipient peer models. When absent the payload omits the
        key and MSWM is left unchanged for this action.
        """

        payload: dict = {"recipient_id": recipient_id, "content": content}
        if mentioned_items:
            payload["mentioned_items"] = list(mentioned_items)
        return await self._record_action(
            agent_id=sender_id,
            action_type=ActionType.OUTBOUND_MESSAGE,
            payload=payload,
            id_prefix="act",
            hook_target_content=content,
            source_action_ids=source_action_ids,
        )

    async def record_tool_call(
        self,
        *,
        agent_id: str,
        tool_name: str,
        arguments: dict,
        source_action_ids: list[str] | None = None,
    ) -> RecordOutcome:
        """Append a ``TOOL_CALL`` ActionRecord if the session is audited.

        Under BASELINE returns an empty outcome with no log append. Under
        PASSIVE or ENFORCE the record is appended and any ``tool``-kind
        hooks run. Under ENFORCE a ``block`` verdict sets ``blocked=True``
        on the outcome and suppresses the TOOL_CALL row so the caller can
        short-circuit the MCP dispatch; ``rewrite`` verdicts are logged as
        POLICY_DECISION rows but do not currently rewrite the persisted
        arguments (no tool-rewrite semantics defined).
        """

        hook_target = f"{tool_name}({arguments!r})"
        return await self._record_action(
            agent_id=agent_id,
            action_type=ActionType.TOOL_CALL,
            payload={"tool_name": tool_name, "arguments": arguments},
            id_prefix="tc",
            hook_target_content=hook_target,
            source_action_ids=source_action_ids,
        )

    async def record_tool_observation(
        self,
        *,
        agent_id: str,
        tool_call_action_id: str | None,
        tool_name: str,
        observation: str,
        source_action_ids: list[str] | None = None,
    ) -> RecordOutcome:
        """Append a ``TOOL_OBSERVATION_RETURN`` ActionRecord, if audited.

        Payload mirrors v1's ``AuditedMessageBus.record_tool_observation``:
        ``{tool_call_action_id, tool_name, observation}``. Baseline returns
        an empty outcome; passive/enforce append and return the new
        ``action_id``. Hooks are not evaluated on returns: the call itself
        was the decision point.

        TODO(F-pair): ``tool_call_action_id`` is recorded verbatim and
        not yet validated against existing ``TOOL_CALL`` records in the
        action log. Call/return pairing verification belongs in the
        MSWM-aware attribution phase (see Phase F in the plan), where
        the attribution graph walker already rebuilds tool call/return
        edges.
        """

        return await self._record_action(
            agent_id=agent_id,
            action_type=ActionType.TOOL_OBSERVATION_RETURN,
            payload={
                "tool_call_action_id": tool_call_action_id,
                "tool_name": tool_name,
                "observation": observation,
            },
            id_prefix="tr",
            hook_target_content=observation,
            source_action_ids=source_action_ids,
        )

    async def record_memory_write(
        self,
        *,
        agent_id: str,
        content: str,
        tags: list[str] | None = None,
        source_action_ids: list[str] | None = None,
    ) -> RecordOutcome:
        """Append a ``MEMORY_WRITE`` ActionRecord, if audited.

        ``tags`` is normalized to an empty list when absent so downstream
        consumers always see a list. Baseline returns an empty outcome.
        Memory-kind hooks may rewrite the content or block the write under
        ENFORCE; PASSIVE logs the verdict but always persists the original.
        """

        return await self._record_action(
            agent_id=agent_id,
            action_type=ActionType.MEMORY_WRITE,
            payload={"content": content, "tags": list(tags) if tags else []},
            id_prefix="mem",
            hook_target_content=content,
            source_action_ids=source_action_ids,
        )

    async def record_llm_call(
        self,
        *,
        agent_id: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        model: str,
        cached_tokens: int = 0,
        source_action_ids: list[str] | None = None,
    ) -> RecordOutcome:
        """Append an ``LLM_CALL`` ActionRecord with token accounting, if audited.

        The payload carries five accounting fields (``input_tokens``,
        ``output_tokens``, ``cached_tokens``, ``latency_ms``, ``model``).
        ``cached_tokens`` defaults to 0 when the caller omits it. Baseline
        returns an empty outcome. LLM calls are not hook-scoped.
        """

        return await self._record_action(
            agent_id=agent_id,
            action_type=ActionType.LLM_CALL,
            payload={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cached_tokens": cached_tokens,
                "latency_ms": latency_ms,
                "model": model,
            },
            id_prefix="llm",
            hook_target_content=None,
            source_action_ids=source_action_ids,
        )

    async def _record_action(
        self,
        *,
        agent_id: str,
        action_type: ActionType,
        payload: dict,
        id_prefix: str,
        hook_target_content: str | None,
        source_action_ids: list[str] | None = None,
    ) -> RecordOutcome:
        """Shared helper: append an ActionRecord under PASSIVE or ENFORCE.

        Steps, mirroring the v1 ``AuditedMessageBus``:

        1. Baseline short-circuit (no log, empty outcome).
        2. Mint a stable ``action_id`` up front so every POLICY_DECISION
           emitted here can reference the target action even when that
           target is ultimately blocked (no row written).
        3. For each hook matching ``_HOOK_KIND_FOR_ACTION[action_type]``,
           evaluate against a provisional ActionRecord whose payload carries
           the CURRENT (post-previous-rewrite) content under ENFORCE or the
           ORIGINAL content under PASSIVE, emit a POLICY_DECISION row to
           primary + shadow + cassette, and update the rewrite/block state.
        4. If blocked under ENFORCE, return early — no primary record is
           appended.
        5. Append the final record to primary log, shadow log, and cassette.

        Under BASELINE this always returns an empty :class:`RecordOutcome`.
        """

        if self.condition == AuditCondition.BASELINE or self.action_log is None:
            return RecordOutcome()

        # Phase tracker is always present under passive/enforce because
        # Session.build wires one; but be defensive and fall back so a
        # hand-constructed Session (unit tests) does not crash.
        social_phase = (
            self.phase_tracker.current_phase()
            if self.phase_tracker is not None
            else SocialPhase.DISCOVERY
        )
        # TODO(runtime-turn): once the gateway runtime exposes a per-scenario
        # turn counter, call ``self.phase_tracker.advance_to_turn(turn)`` from
        # the runtime loop before record_* so the schedule-driven phase
        # changes land. The tracker exposes ``advance_to_turn`` already; this
        # is purely a plumbing gap.

        action_id = f"{id_prefix}-{uuid.uuid4().hex[:12]}"
        hook_kind = _HOOK_KIND_FOR_ACTION.get(action_type)
        sources = list(source_action_ids or [])

        original_content = hook_target_content
        current_content = hook_target_content
        blocked = False

        # Build a provisional representing the current action so MSWM can
        # update immediately and so hooks can see the fresh state (spec §2.6
        # explicitly says MSWM is updated before policy hooks run). We
        # rebuild the provisional inside the hook loop when a rewrite
        # composes, but the MSWM update uses the ORIGINAL provisional only
        # once — MSWM models what the agent intends, not the rewriter's
        # edits.
        initial_provisional = ActionRecord(
            action_id=action_id,
            prev_hash=self.action_log.head_hash(agent_id),
            agent_id=agent_id,
            action_type=action_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=social_phase,
            payload=dict(payload),
            integrity_level=IntegrityLevel.HASH_CHAINED,
            source_action_ids=sources,
        )
        self.mswm.on_action(initial_provisional)

        if hook_kind is not None and self.hooks:
            for hook in self.hooks:
                if getattr(hook, "hook_kind", "message") != hook_kind:
                    continue
                # Build the provisional the hook sees. Under PASSIVE the
                # provisional carries the ORIGINAL content (rewrites do not
                # compose because they do not propagate); under ENFORCE
                # it carries the CURRENT (post-previous-rewrite) content
                # so a rewrite chain composes.
                provisional_payload = dict(payload)
                if hook_target_content is not None:
                    content_key = _content_key_for_action(action_type)
                    if content_key is not None:
                        provisional_payload[content_key] = current_content

                provisional = ActionRecord(
                    action_id=action_id,
                    prev_hash=self.action_log.head_hash(agent_id),
                    agent_id=agent_id,
                    action_type=action_type,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    execution_phase=ExecutionPhase.NOMINAL,
                    social_phase=social_phase,
                    payload=provisional_payload,
                    integrity_level=IntegrityLevel.HASH_CHAINED,
                    source_action_ids=sources,
                )
                decision: PolicyDecision = hook.evaluate(
                    action=provisional, context={"mswm": self.mswm}
                )

                post_content = (
                    decision.rewritten_content
                    if decision.verdict == PolicyVerdict.REWRITE
                    else None
                )
                self._append_policy_decision(
                    agent_id=agent_id,
                    decision=decision,
                    target_action_id=action_id,
                    social_phase=social_phase,
                    original_content=original_content,
                    post_content=post_content,
                )

                if self.condition == AuditCondition.ENFORCE:
                    if decision.verdict == PolicyVerdict.BLOCK:
                        blocked = True
                        break
                    if (
                        decision.verdict == PolicyVerdict.REWRITE
                        and decision.rewritten_content is not None
                    ):
                        current_content = decision.rewritten_content

        if blocked:
            # No primary record, no cassette line for the action itself;
            # the POLICY_DECISION rows above preserve the evidence. Revert
            # the MSWM update we did pre-hook so the state reflects "action
            # never happened" from the peer's perspective.
            self.mswm.revert_action(initial_provisional)
            return RecordOutcome(action_id=None, blocked=True)

        # Build the final payload: under ENFORCE with a rewrite, the
        # persisted content is the post-rewrite content; otherwise the
        # original payload wins.
        final_payload = dict(payload)
        if (
            self.condition == AuditCondition.ENFORCE
            and hook_target_content is not None
            and current_content != original_content
        ):
            content_key = _content_key_for_action(action_type)
            if content_key is not None:
                final_payload[content_key] = current_content

        record = ActionRecord(
            action_id=action_id,
            prev_hash=self.action_log.head_hash(agent_id),
            agent_id=agent_id,
            action_type=action_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=social_phase,
            payload=final_payload,
            integrity_level=IntegrityLevel.HASH_CHAINED,
            source_action_ids=sources,
        )
        self.action_log.append(record)

        if self.shadow_log is not None:
            shadow_rec = record.model_copy(
                update={"prev_hash": self.shadow_log.head_hash(agent_id)}
            )
            self.shadow_log.append(shadow_rec)

        if self.cassette is not None:
            self.cassette.record(kind=action_type.value, payload=final_payload)

        rewritten = (
            current_content
            if (
                self.condition == AuditCondition.ENFORCE
                and hook_target_content is not None
                and current_content != original_content
            )
            else None
        )
        return RecordOutcome(
            action_id=action_id,
            rewritten_content=rewritten,
            blocked=False,
        )

    def _append_policy_decision(
        self,
        *,
        agent_id: str,
        decision: PolicyDecision,
        target_action_id: str,
        social_phase: SocialPhase,
        original_content: str | None,
        post_content: str | None,
    ) -> None:
        """Append a POLICY_DECISION row to primary + shadow logs + cassette.

        Payload shape matches the v1 ``AuditedMessageBus`` for continuity
        with downstream analysis code (see ``clawsocialarena/audit`` and
        Phase E/F scorers): ``verdict``, ``policy_id``, ``reason``,
        ``target_action_id``, ``original_content``, ``post_content``.
        """

        if self.action_log is None:
            return
        pd_payload: dict = {
            "verdict": decision.verdict.value,
            "policy_id": decision.policy_id,
            "reason": decision.reason,
            "target_action_id": target_action_id,
            "original_content": original_content,
            "post_content": post_content,
        }
        rec = ActionRecord(
            action_id=f"pol-{uuid.uuid4().hex[:12]}",
            prev_hash=self.action_log.head_hash(agent_id),
            agent_id=agent_id,
            action_type=ActionType.POLICY_DECISION,
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=social_phase,
            payload=pd_payload,
            integrity_level=IntegrityLevel.HASH_CHAINED,
        )
        self.action_log.append(rec)
        if self.shadow_log is not None:
            shadow_rec = rec.model_copy(
                update={"prev_hash": self.shadow_log.head_hash(agent_id)}
            )
            self.shadow_log.append(shadow_rec)
        if self.cassette is not None:
            self.cassette.record(
                kind=ActionType.POLICY_DECISION.value, payload=pd_payload
            )


def _content_key_for_action(action_type: ActionType) -> str | None:
    """Return the payload key the hook rewrite should replace, or ``None``.

    Outbound messages carry the evidence in ``payload["content"]``; memory
    writes do the same. Tool calls and tool observations do not have a
    single content field that rewrite semantics can mutate, so we return
    ``None`` and let POLICY_DECISION capture the evidence only.
    """

    if action_type in (
        ActionType.OUTBOUND_MESSAGE,
        ActionType.MEMORY_WRITE,
        ActionType.MEMORY_COMPRESSION,
        ActionType.SUMMARY_WRITE,
    ):
        return "content"
    return None
