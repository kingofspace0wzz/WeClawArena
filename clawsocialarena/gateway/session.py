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

Task A3 extends this object with lazily-created per-recipient
``asyncio.Queue`` inboxes and a ``record_outbound`` helper that wraps
``ActionLog.append`` with an ``OUTBOUND_MESSAGE`` record. Policy hooks,
phase tagging, shadow double-write, and cassette recording are deliberately
left out: those land in A4, A5, and C5.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.phase_tracker import PhaseTracker
from clawsocialarena.audit.shadow_log import ShadowLog
from clawsocialarena.gateway.cassette import CassetteRecorder
from clawsocialarena.gateway.mcp_host import McpHost
from clawsocialarena.protocols.policy_hook import PolicyHook
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    AuditCondition,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


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

    @classmethod
    def build(
        cls,
        scenario_id: str,
        condition: AuditCondition,
        *,
        db_path: str | Path,
        phase_schedule: list[dict] | None = None,
        work_dir: Path | str | None = None,
    ) -> "Session":
        """Construct a Session with substrate wired per ``condition``.

        Under BASELINE every substrate field stays ``None`` and ``db_path`` is
        ignored; under PASSIVE or ENFORCE the full audit stack is created,
        with the shadow log persisted alongside the primary log as
        ``{db_path.stem}.shadow.db`` in the same directory. When ``work_dir``
        is supplied under a non-baseline condition, a
        :class:`CassetteRecorder` is attached that writes a
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

    def record_outbound(
        self,
        *,
        sender_id: str,
        recipient_id: str,
        content: str,
    ) -> str | None:
        """Append an ``OUTBOUND_MESSAGE`` ActionRecord for a send, if audited.

        Under BASELINE this is a no-op and returns ``None``: the baseline
        condition simulates "deployment without audit infrastructure" so no
        log exists to append to. Under PASSIVE or ENFORCE the record is
        appended to the primary ``ActionLog`` and the assigned ``action_id``
        is returned.

        Policy hooks, phase tagging, shadow double-write, and cassette
        recording are deliberately omitted at this stage; they land in
        subsequent tasks (A4 side channels, A5 cassette, C5 MSWM wiring).
        """

        return self._record_action(
            agent_id=sender_id,
            action_type=ActionType.OUTBOUND_MESSAGE,
            payload={"recipient_id": recipient_id, "content": content},
            id_prefix="act",
        )

    def record_tool_call(
        self,
        *,
        agent_id: str,
        tool_name: str,
        arguments: dict,
    ) -> str | None:
        """Append a ``TOOL_CALL`` ActionRecord if the session is audited.

        Under BASELINE returns ``None`` with no log append, matching the
        semantics of :meth:`record_outbound`. Under PASSIVE or ENFORCE the
        record is appended and its assigned ``action_id`` is returned so
        the caller (and any later ``record_tool_observation``) can link to
        it. Policy hooks, phase tagging, shadow double-write, and cassette
        recording are deliberately omitted at this stage.
        """

        return self._record_action(
            agent_id=agent_id,
            action_type=ActionType.TOOL_CALL,
            payload={"tool_name": tool_name, "arguments": arguments},
            id_prefix="tc",
        )

    def record_tool_observation(
        self,
        *,
        agent_id: str,
        tool_call_action_id: str | None,
        tool_name: str,
        observation: str,
    ) -> str | None:
        """Append a ``TOOL_OBSERVATION_RETURN`` ActionRecord, if audited.

        Payload mirrors v1's ``AuditedMessageBus.record_tool_observation``:
        ``{tool_call_action_id, tool_name, observation}``. Baseline returns
        ``None``; passive/enforce append and return the new ``action_id``.

        ``tool_call_action_id`` accepts ``None`` so callers in the
        ``/mcp/{tool_name}`` route can thread the result of
        :meth:`record_tool_call` through unchanged. Under BASELINE the
        record is not written so the ``None`` is never serialized; under
        PASSIVE or ENFORCE the prior ``record_tool_call`` always yields a
        concrete id, so the ``None`` branch is unreachable in practice
        and the type simply relaxes the contract to match.

        TODO(F-pair): ``tool_call_action_id`` is recorded verbatim and
        not yet validated against existing ``TOOL_CALL`` records in the
        action log. Call/return pairing verification belongs in the
        MSWM-aware attribution phase (see Phase F in the plan), where
        the attribution graph walker already rebuilds tool call/return
        edges.
        """

        return self._record_action(
            agent_id=agent_id,
            action_type=ActionType.TOOL_OBSERVATION_RETURN,
            payload={
                "tool_call_action_id": tool_call_action_id,
                "tool_name": tool_name,
                "observation": observation,
            },
            id_prefix="tr",
        )

    def record_memory_write(
        self,
        *,
        agent_id: str,
        content: str,
        tags: list[str] | None = None,
    ) -> str | None:
        """Append a ``MEMORY_WRITE`` ActionRecord, if audited.

        ``tags`` is normalized to an empty list when absent so downstream
        consumers always see a list. Baseline returns ``None``.
        """

        return self._record_action(
            agent_id=agent_id,
            action_type=ActionType.MEMORY_WRITE,
            payload={"content": content, "tags": list(tags) if tags else []},
            id_prefix="mem",
        )

    def record_llm_call(
        self,
        *,
        agent_id: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        model: str,
        cached_tokens: int = 0,
    ) -> str | None:
        """Append an ``LLM_CALL`` ActionRecord with token accounting, if audited.

        The payload carries five accounting fields (``input_tokens``,
        ``output_tokens``, ``cached_tokens``, ``latency_ms``, ``model``).
        ``cached_tokens`` defaults to 0 when the caller omits it. Baseline
        returns ``None`` and writes nothing.
        """

        return self._record_action(
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
        )

    def _record_action(
        self,
        *,
        agent_id: str,
        action_type: ActionType,
        payload: dict,
        id_prefix: str,
    ) -> str | None:
        """Shared helper: append an ActionRecord under PASSIVE or ENFORCE.

        Returns the generated ``action_id`` on append, or ``None`` under
        BASELINE (no-op). Uses the same construction shape as the v1
        ``AuditedMessageBus`` (hash-chained integrity, NOMINAL execution
        phase, DISCOVERY social phase placeholder until Task A6 wires the
        ``PhaseTracker`` through).
        """

        if self.condition == AuditCondition.BASELINE or self.action_log is None:
            return None

        action_id = f"{id_prefix}-{uuid.uuid4().hex[:12]}"
        record = ActionRecord(
            action_id=action_id,
            prev_hash=self.action_log.head_hash(agent_id),
            agent_id=agent_id,
            action_type=action_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=SocialPhase.DISCOVERY,  # TODO(A6): phase_tracker.current_phase(turn_index)
            payload=payload,
            integrity_level=IntegrityLevel.HASH_CHAINED,
        )
        self.action_log.append(record)
        if self.cassette is not None:
            self.cassette.record(kind=action_type.value, payload=payload)
        return action_id
