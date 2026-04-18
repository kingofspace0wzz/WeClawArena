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
from typing import Any, Iterable, Literal

from clawsocialarena.types import ActionRecord, ActionType, SocialPhase


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
        # Self-knowledge bag:
        # ``self_knowledge[agent_id] -> set[(item_id, action_id)]``.
        # This is ADDITIONAL state orthogonal to ``state[i][j]``. It captures
        # items an agent knows about from non-peer sources (memory reads,
        # retrieval) so downstream decidability checks can distinguish
        # "known" from "not known" without conflating that with
        # "learned from peer j". Storing the introducing ``action_id`` alongside
        # the item lets Phase F attribution trace a self-known item back to the
        # exact memory_write / retrieval_fetch / summary_write that introduced
        # it.
        self.self_knowledge: dict[str, set[tuple[str, str]]] = {}

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

    def on_action(self, action: ActionRecord) -> None:
        """Apply ``action`` to MSWM state.

        Dispatches on ``action.action_type``. Unknown types are ignored so
        the gateway can thread every record through MSWM without a type
        allowlist upstream.

        For OUTBOUND_MESSAGE, ``payload.mentioned_items`` (optional list of
        item_id strings) drives the disclosure update:

        - ``state[sender][recipient].items_told_to_j`` gains each
          ``(item_id, action_id)`` tuple.
        - ``state[recipient][sender].items_learned_from_j`` gains the
          symmetric tuple, so the recipient's peer model reflects what it
          now knows came from the sender.

        If ``mentioned_items`` is absent (v1 payload convention), no MSWM
        update is performed. This keeps MSWM backward-compatible with the
        existing outbound payload that carries only ``recipient_id`` and
        ``content``.
        """

        if action.action_type == ActionType.OUTBOUND_MESSAGE:
            self._on_outbound_message(action)
        elif action.action_type in (
            ActionType.MEMORY_WRITE,
            ActionType.SUMMARY_WRITE,
            ActionType.MEMORY_COMPRESSION,
        ):
            # Writer-only update: the agent reinforces its own knowledge of
            # items in the payload. These actions do NOT disclose anything
            # to peers — they are private to the agent's own memory store.
            self._on_self_knowledge(action, key="mentioned_items")
        elif action.action_type == ActionType.RETRIEVAL_FETCH:
            # Retrieval brings external items into the agent's own knowledge
            # but — critically — does not broadcast anything to peers.
            # ``items_exposed`` is the payload convention: a list of item_id
            # strings surfaced by the retrieval result.
            self._on_self_knowledge(action, key="items_exposed")

    def _on_outbound_message(self, action: ActionRecord) -> None:
        payload = action.payload
        recipient_id = payload.get("recipient_id")
        mentioned = payload.get("mentioned_items") or []
        if not recipient_id or not isinstance(recipient_id, str):
            return
        if not mentioned:
            return
        sender_id = action.agent_id
        action_id = action.action_id
        sender_model = self.get(sender_id, recipient_id)
        recipient_model = self.get(recipient_id, sender_id)
        for item_id in mentioned:
            if not isinstance(item_id, str):
                continue
            sender_model.items_told_to_j.add((item_id, action_id))
            recipient_model.items_learned_from_j.add((item_id, action_id))
        sender_model.phase_of_last_interaction = action.social_phase
        recipient_model.phase_of_last_interaction = action.social_phase

    def revert_action(self, action: ActionRecord) -> None:
        """Undo any MSWM update previously applied for ``action``.

        Used by :class:`clawsocialarena.gateway.session.Session` when an
        ENFORCE-mode hook BLOCKs an action after MSWM has already updated
        to reflect it. The revert is surgical: it removes tuples keyed by
        ``(item_id, action.action_id)`` rather than clearing entire sets.

        Self-knowledge reverts are best-effort: retrieval and memory reads
        are not atomically undoable (the agent *did* observe the content),
        so for now we only undo peer-facing state. Memory writes that were
        blocked after MSWM processed them keep their self-knowledge bag
        unchanged, which is the safe conservative choice.
        """

        if action.action_type != ActionType.OUTBOUND_MESSAGE:
            return
        payload = action.payload
        recipient_id = payload.get("recipient_id")
        mentioned = payload.get("mentioned_items") or []
        if not recipient_id or not isinstance(recipient_id, str) or not mentioned:
            return
        sender_id = action.agent_id
        action_id = action.action_id
        sender_model = self.state.get(sender_id, {}).get(recipient_id)
        recipient_model = self.state.get(recipient_id, {}).get(sender_id)
        for item_id in mentioned:
            if not isinstance(item_id, str):
                continue
            if sender_model is not None:
                sender_model.items_told_to_j.discard((item_id, action_id))
            if recipient_model is not None:
                recipient_model.items_learned_from_j.discard((item_id, action_id))

    def _on_self_knowledge(self, action: ActionRecord, *, key: str) -> None:
        """Mark ``action.agent_id`` as knowing each item in ``payload[key]``.

        Self-knowledge is orthogonal to peer disclosure: memory writes,
        summaries, and retrieval fetches update what the agent privately
        knows without notifying any peer. The payload key differs per
        action type (``mentioned_items`` for memory/summary, ``items_exposed``
        for retrieval) so the caller selects the right field.

        Each item is stored as ``(item_id, action.action_id)`` so Phase F
        attribution can walk from a self-known item back to the introducing
        action.
        """

        items = action.payload.get(key) or []
        if not items:
            return
        bag = self.self_knowledge.setdefault(action.agent_id, set())
        for item_id in items:
            if isinstance(item_id, str):
                bag.add((item_id, action.action_id))

    # ------------------------------------------------------------------
    # Joint decidability (SAF dim 2 / ψ)
    # ------------------------------------------------------------------
    def known_items(self, agent_id: str) -> set[str]:
        """Return every item ``agent_id`` knows, across all sources.

        Union of:
        - items in ``self_knowledge[agent_id]`` (memory, summary, retrieval),
          with provenance stripped.
        - items in ``MSWM[agent_id][j].items_learned_from_j`` for every
          peer j (things ``agent_id`` has been told).
        - items ``agent_id`` has TOLD (``items_told_to_j``): the agent
          necessarily knew them to tell them in the first place.
        """

        known: set[str] = set()
        known.update(item for item, _ in self.self_knowledge.get(agent_id, set()))
        peers = self.state.get(agent_id, {})
        for peer_model in peers.values():
            known.update(item for item, _ in peer_model.items_learned_from_j)
            known.update(item for item, _ in peer_model.items_told_to_j)
        return known

    def known_items_with_provenance(
        self, agent_id: str
    ) -> set[tuple[str, str]]:
        """Return ``(item_id, action_id)`` tuples for every item ``agent_id`` knows.

        Union of self-knowledge plus every peer-sourced tuple. Used by
        attribution code that needs to walk back to the introducing action.
        """

        tuples: set[tuple[str, str]] = set()
        tuples.update(self.self_knowledge.get(agent_id, set()))
        peers = self.state.get(agent_id, {})
        for peer_model in peers.values():
            tuples.update(peer_model.items_learned_from_j)
            tuples.update(peer_model.items_told_to_j)
        return tuples

    def _has_any_entry(self, agent_id: str) -> bool:
        """Return True if MSWM has ANY record of ``agent_id``.

        Record means either at least one self-knowledge tuple or at least
        one peer model (even if its contents are empty). If the agent has
        never appeared on either side of an action, decidability is
        undecidable because the model carries no evidence about the agent
        at all.
        """

        if self.self_knowledge.get(agent_id):
            return True
        if self.state.get(agent_id):
            return True
        # The agent may appear only as a peer of some other agent (i.e.
        # someone's told_to/learned_from points at agent_id). Walk the
        # state to check.
        for peers in self.state.values():
            if agent_id in peers:
                return True
        return False

    def _item_observed_anywhere(self, item_id: str) -> bool:
        """Return True if ``item_id`` appears anywhere in MSWM.

        "Anywhere" means any self_knowledge bag, any ``items_told_to_j``
        set, or any ``items_learned_from_j`` set across all agents. Used to
        distinguish "definitely unknown" (item seen in some channel, just
        not by ``for_agent``) from "never observed" (no evidence anywhere;
        the model cannot rule for or against the inference).
        """

        for bag in self.self_knowledge.values():
            if any(item == item_id for item, _ in bag):
                return True
        for peers in self.state.values():
            for peer_model in peers.values():
                if any(item == item_id for item, _ in peer_model.items_told_to_j):
                    return True
                if any(item == item_id for item, _ in peer_model.items_learned_from_j):
                    return True
        return False

    def joint_decidability(
        self, agent_id: str, predicate: dict[str, Any]
    ) -> Literal["decidable", "undecidable", "violated"]:
        """Evaluate whether ``agent_id`` can jointly decide a predicate.

        Predicate schema (adapted from spec §3.2 dim 2):

        ``{"type": "must_not_decide" | "must_decide",``
        `` "for_agent": str,``
        `` "forbidden_inference": list[str]  # list of item ids}``

        Semantics:

        - ``must_not_decide``: the policy author asserts ``for_agent`` MUST
          NOT be able to combine every item in ``forbidden_inference`` into
          a single inference. Return values:

          - ``violated`` — ``for_agent`` already knows EVERY item in the
            forbidden set (it can make the inference now).
          - ``decidable`` — every referenced item has a definite
            known/unknown answer for ``for_agent`` and at least one is
            unknown. The forbidden inference cannot be formed.
          - ``undecidable`` — the model carries no evidence about
            ``for_agent`` (the agent has no MSWM entry at all) OR at least
            one referenced item has never been observed in any channel, so
            the status of "known" vs "not known" is not pinned down.

        - ``must_decide``: symmetric flip. ``violated`` if the predicate is
          decidable and ``for_agent`` lacks any item; ``decidable`` if
          ``for_agent`` knows all of them; ``undecidable`` under the same
          conditions as above.

        ``agent_id`` is the SUBJECT of the query (the policy's point of
        view). For the vignette scenarios the subject and ``for_agent``
        can differ (e.g. gateway queries "is A's policy about C violated?"
        so ``agent_id="A"``, ``for_agent="C"``); we accept both and use
        ``for_agent`` when present, falling back to ``agent_id`` otherwise.
        """

        ptype = predicate.get("type")
        target_agent = predicate.get("for_agent") or agent_id
        forbidden = list(predicate.get("forbidden_inference") or [])
        if ptype not in ("must_not_decide", "must_decide"):
            return "undecidable"
        if not forbidden:
            # An empty forbidden set is vacuously true/false depending on
            # polarity. Treat as decidable: no items to combine means the
            # inference cannot be formed.
            return "decidable" if ptype == "must_not_decide" else "violated"

        # Undecidability path: the target agent has no MSWM footprint at
        # all, OR at least one referenced item has never been seen in any
        # channel. In both cases we lack sufficient evidence to rule.
        if not self._has_any_entry(target_agent):
            return "undecidable"
        for item in forbidden:
            if not self._item_observed_anywhere(item):
                return "undecidable"

        known = self.known_items(target_agent)
        can_derive = all(item in known for item in forbidden)
        if ptype == "must_not_decide":
            return "violated" if can_derive else "decidable"
        # must_decide
        return "decidable" if can_derive else "violated"
