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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.phase_tracker import PhaseTracker
from clawsocialarena.audit.shadow_log import ShadowLog
from clawsocialarena.protocols.policy_hook import PolicyHook
from clawsocialarena.types import AuditCondition


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
    """

    scenario_id: str
    condition: AuditCondition
    action_log: ActionLog | None = None
    shadow_log: ShadowLog | None = None
    phase_tracker: PhaseTracker | None = None
    cassette: object | None = None
    hooks: list[PolicyHook] = field(default_factory=list)

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
