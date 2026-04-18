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
    """

    scenario_id: str
    condition: AuditCondition
    action_log: ActionLog | None = None
    shadow_log: ShadowLog | None = None
    phase_tracker: PhaseTracker | None = None
    cassette: object | None = None
    hooks: list[PolicyHook] = field(default_factory=list)
    inboxes: dict[str, asyncio.Queue[tuple[str, str]]] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        scenario_id: str,
        condition: AuditCondition,
        *,
        db_path: str | Path,
        phase_schedule: list[dict] | None = None,
    ) -> "Session":
        """Construct a Session with substrate wired per ``condition``.

        Under BASELINE every substrate field stays ``None`` and ``db_path`` is
        ignored; under PASSIVE or ENFORCE the full audit stack is created,
        with the shadow log persisted alongside the primary log as
        ``{db_path.stem}.shadow.db`` in the same directory.

        Args:
            scenario_id: Stable identifier for the scenario.
            condition: Audit condition governing substrate wiring.
            db_path: Filesystem path for the primary ``ActionLog`` DB.
                Ignored under BASELINE.
            phase_schedule: Optional phase schedule (as used by
                ``PhaseTracker.from_schedule``). When absent a plain
                :class:`PhaseTracker` is created.
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
        return cls(
            scenario_id=scenario_id,
            condition=condition,
            action_log=action_log,
            shadow_log=shadow_log,
            phase_tracker=phase_tracker,
        )

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

        if self.condition == AuditCondition.BASELINE or self.action_log is None:
            return None

        action_id = f"act-{uuid.uuid4().hex[:12]}"
        record = ActionRecord(
            action_id=action_id,
            prev_hash=self.action_log.head_hash(sender_id),
            agent_id=sender_id,
            action_type=ActionType.OUTBOUND_MESSAGE,
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=SocialPhase.DISCOVERY,  # TODO(A6): phase_tracker.current_phase(turn_index)
            payload={"recipient_id": recipient_id, "content": content},
            integrity_level=IntegrityLevel.HASH_CHAINED,
        )
        self.action_log.append(record)
        return action_id
