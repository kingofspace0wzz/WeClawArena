"""Multi-Party Social World Model (MSWM) — runtime centerpiece.

For each ordered pair of agents ``(i, j)`` the gateway maintains a per-peer
mental model of what ``i`` believes ``j`` knows, has committed to, and last
interacted with. Spec §2.6 is the canonical source of truth; this module is
the Python implementation.

The MSWM is updated online by :class:`clawsocialarena.gateway.session.Session`
immediately after each :class:`~clawsocialarena.types.ActionRecord` is appended
to the primary log, BEFORE policy hooks fire. That ordering lets a hook query
the freshly-updated MSWM and make a joint-decidability verdict against the
current state (spec §2.6 "is updated online ... before policy hooks run").

Two SAF dimensions are decidable only with MSWM state:

- **ψ — Epistemics-aware Policy Checkability.** See :meth:`MSWM.joint_decidability`.
- **τ — Inference-Chain Responsibility Attribution.** See
  :mod:`clawsocialarena.audit.attribution`, which walks MSWM references
  back through ``items_learned_from_j`` to attribute root causes.

The state is kept entirely in-memory for the lifetime of a session. Cassettes
and the action log are the durable artifacts; MSWM is rebuilt from the log at
evaluation time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from clawsocialarena.types import SocialPhase


@dataclass
class PeerModel:
    """``MSWM[i][j]`` — what agent ``i`` believes about peer ``j``.

    Fields track the spec §2.6 schema verbatim.

    Attributes:
        items_told_to_j: Set of ``(item_id, action_id)`` tuples — items
            ``i`` has disclosed to ``j`` via ``outbound_message`` actions.
            Each tuple pins the disclosing action so attribution can walk
            back to the exact source.
        items_learned_from_j: Symmetric set tracked by the recipient side:
            items ``i`` has learned from ``j``'s outbound messages.
        commitments_to_j: Set of ``(commitment_id, phase, action_id)``
            tuples recording commitments ``i`` has made to ``j`` within a
            social phase. Used by future phase-aware scorers; this module
            only owns the storage.
        phase_of_last_interaction: The SocialPhase at which ``i`` and
            ``j`` last interacted, or ``None`` before first contact.
        trust_estimate: Reserved for affinity-modulated scenarios
            (spec §4.2 AM category). Defaults to ``0.5`` (neutral).
    """

    items_told_to_j: set[tuple[str, str]] = field(default_factory=set)
    items_learned_from_j: set[tuple[str, str]] = field(default_factory=set)
    commitments_to_j: set[tuple[str, str, str]] = field(default_factory=set)
    phase_of_last_interaction: SocialPhase | None = None
    trust_estimate: float = 0.5


class MSWM:
    """Online Multi-Party Social World Model.

    Stores a sparse ``state[i][j] -> PeerModel`` dict. Defaults are created
    lazily on access, so the dict only contains pairs that have actually
    interacted. ``get`` is the idiomatic accessor and always returns a
    concrete :class:`PeerModel` (materializing a default-initialized one
    on miss).

    The module also carries a small top-level ``self_knowledge`` bag that
    tracks what each agent directly knows (outside peer-disclosure context).
    This is used by RETRIEVAL_FETCH updates, where the agent gains
    knowledge without a peer being involved — see :meth:`on_action`.
    """

    def __init__(self) -> None:
        self.state: dict[str, dict[str, PeerModel]] = {}
        # Self-knowledge bag: ``self_knowledge[agent_id] -> set[item_id]``.
        # This is ADDITIONAL state orthogonal to ``state[i][j]``. It captures
        # items an agent knows about from non-peer sources (memory reads,
        # retrieval) so that downstream decidability checks can distinguish
        # "known" from "not known" without conflating that with
        # "learned from peer j".
        self.self_knowledge: dict[str, set[str]] = {}

    def get(self, i: str, j: str) -> PeerModel:
        """Return ``MSWM[i][j]``, materializing a default on first access."""

        peers = self.state.setdefault(i, {})
        model = peers.get(j)
        if model is None:
            model = PeerModel()
            peers[j] = model
        return model

    def pairs(self) -> Iterable[tuple[str, str]]:
        """Iterate ordered pairs ``(i, j)`` present in the state dict."""

        for i, peers in self.state.items():
            for j in peers.keys():
                yield (i, j)
