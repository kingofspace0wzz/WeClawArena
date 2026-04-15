"""PolicyRegistry: flat and phase-scoped predicates for SAF scoring."""

from __future__ import annotations

from typing import Callable
from pydantic import BaseModel, ConfigDict

from clawsocialarena.types import ActionRecord, SocialPhase


class FlatPolicy(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    policy_id: str
    predicate: Callable[[ActionRecord, dict], bool]
    required_fields: set[str]


class PhaseScopedPolicy(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    policy_id: str
    phase: SocialPhase
    predicate: Callable[[ActionRecord, dict], bool]
    required_fields: set[str]


class PolicyRegistry:
    """Holds flat + phase-scoped policies; evaluates an action against them."""

    def __init__(self) -> None:
        self._flat: list[FlatPolicy] = []
        self._scoped: list[PhaseScopedPolicy] = []

    def register_flat(self, p: FlatPolicy) -> None:
        self._flat.append(p)

    def register_phase_scoped(self, p: PhaseScopedPolicy) -> None:
        self._scoped.append(p)

    def evaluate_flat(
        self, action: ActionRecord, *, ctx: dict
    ) -> dict[str, bool | None]:
        return {p.policy_id: bool(p.predicate(action, ctx)) for p in self._flat}

    def evaluate_phase_scoped(
        self,
        action: ActionRecord,
        *,
        ctx: dict,
        current_phase: SocialPhase,
    ) -> dict[str, bool | None]:
        out: dict[str, bool | None] = {}
        for p in self._scoped:
            if p.phase == current_phase:
                out[p.policy_id] = bool(p.predicate(action, ctx))
            else:
                out[p.policy_id] = None  # not applicable in this phase
        return out

    @property
    def flat_policies(self) -> list[FlatPolicy]:
        return list(self._flat)

    @property
    def scoped_policies(self) -> list[PhaseScopedPolicy]:
        return list(self._scoped)
