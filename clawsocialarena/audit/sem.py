"""Simplified SEM (Social Epistemic Modeling) state store for Phase 2.

Full SEM (with inference chains, ownership transitions, propagation probes)
is documented in the spec and will be extended in Phase 3/4. For Phase 2 we
need enough shape to make Policy Checkability computable: per-agent beliefs
about who owns which item and at what level of certainty.

Vendoring status: clawsocialos SEM was partially designed but unmerged at
time of this task (no SEM module exists under clawsocialos/socialdyn/ or
elsewhere in that codebase). Stubbed here from scratch rather than vendored.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class OwnershipState(StrEnum):
    """Agent's belief about who owns / has rights to an item.

    Mirrors the SEM ownership lattice in the spec:
      - UNKNOWN: no belief recorded
      - INFERRED: belief derived from indirect evidence
      - FULL: belief derived from direct disclosure
      - SELF: agent itself owns the item
      - INVALID: belief was contradicted; ownership claim rejected
    """

    UNKNOWN = "unknown"
    INFERRED = "inferred"
    FULL = "full"
    SELF = "self"
    INVALID = "invalid"


class SEMStore(BaseModel):
    """agent_id -> (item, owner) -> OwnershipState.

    Stored with string-keyed nested dict because pydantic doesn't support
    tuple keys natively. Keys are joined with '\t' (unambiguous since item
    and owner names can't contain tabs).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    store: dict[str, dict[str, OwnershipState]] = {}

    @staticmethod
    def _k(item: str, owner: str) -> str:
        return f"{item}\t{owner}"

    def set(
        self,
        *,
        agent_id: str,
        item: str,
        owner: str,
        state: OwnershipState,
    ) -> None:
        self.store.setdefault(agent_id, {})[self._k(item, owner)] = state

    def get(self, *, agent_id: str, item: str, owner: str) -> OwnershipState:
        return self.store.get(agent_id, {}).get(
            self._k(item, owner), OwnershipState.UNKNOWN
        )
