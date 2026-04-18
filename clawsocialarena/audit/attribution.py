"""AttributionGraph builder — online MSWM-aware DAG.

REPLACES the v1 attribution module. The Phase C rewrite adds MSWM-aware
edges on top of the v1 causal / proximity fallback: when an outbound action
carries ``mentioned_items``, the MSWM ``items_learned_from_j`` back-index
points at the action_id where the current agent learned each mentioned item,
and that action becomes an additional causal parent. This is how the spec
§2.6 example (C's turn-9 action traces back through B's turn-6 summary to
A's turn-3 disclosure) actually gets derived — the explicit
``source_action_ids`` field may be empty on the harmful action itself.

Backward compatibility:

- The legacy constructor ``AttributionGraphBuilder(cascade_window=N)`` and
  the legacy call ``builder.build(action_log=[...])`` are preserved. When
  MSWM is not supplied, the builder degrades gracefully to the v1
  behavior (causal from source_action_ids + proximity fallback).
- The new idiom is ``AttributionGraphBuilder(action_log=log, mswm=mswm)``
  followed by ``builder.build()`` with no args. Both idioms coexist.

Output shape is unchanged so the existing SAF scorer continues to work:
    {"nodes": [{"id","label","agent_id"}, ...],
     "edges": [{"src","dst","label"}, ...]}
"""

from __future__ import annotations

import logging
from typing import Iterable

from clawsocialarena.audit.mswm import MSWM
from clawsocialarena.types import ActionRecord, ActionType


logger = logging.getLogger(__name__)


class AttributionGraphBuilder:
    """Builds an attribution DAG from an action log and optional MSWM state.

    Two construction patterns are supported:

    1. Phase C idiom (preferred): ``AttributionGraphBuilder(action_log=log,
       mswm=mswm).build()``. ``action_log`` may be a list of ActionRecord
       or an ``ActionLog`` instance; ``mswm`` provides the
       ``items_learned_from_j`` back-references.
    2. Legacy idiom: ``AttributionGraphBuilder(cascade_window=N).build(
       action_log=log)``. No MSWM; causal + proximity fallback only.

    ``cascade_window`` controls the proximity fallback's look-ahead window
    on the legacy path (default 5).
    """

    def __init__(
        self,
        action_log: list[ActionRecord] | None = None,
        mswm: MSWM | None = None,
        *,
        cascade_window: int = 5,
    ) -> None:
        self._action_log = action_log
        self._mswm = mswm
        self.cascade_window = cascade_window

    def build(self, *, action_log: list[ActionRecord] | None = None) -> dict:
        """Produce the DAG. ``action_log`` kwarg supports the legacy call."""

        records = action_log if action_log is not None else self._action_log
        if records is None:
            records = []

        mswm = self._mswm
        # If the caller did not provide an MSWM but provided an action log,
        # rebuild one by replaying the log. Evaluation code paths (post-hoc
        # scoring) use this pattern so that the MSWM reflects exactly what
        # the log implies without a live session context.
        if mswm is None and records:
            rebuilt = MSWM()
            for rec in records:
                rebuilt.on_action(rec)
            mswm = rebuilt

        has_provenance = any(bool(r.source_action_ids) for r in records)
        if has_provenance or (mswm is not None and _mswm_has_links(mswm)):
            return self._build_causal(records, mswm)
        if records:
            logger.debug(
                "AttributionGraphBuilder: no source_action_ids and empty MSWM; "
                "falling back to proximity heuristic (cascade_window=%d).",
                self.cascade_window,
            )
        return self._build_proximity(records)

    # ------------------------------------------------------------------
    # Causal path (explicit provenance + MSWM-derived edges)
    # ------------------------------------------------------------------
    def _build_causal(
        self, action_log: list[ActionRecord], mswm: MSWM | None
    ) -> dict:
        nodes: list[dict] = []
        edges: list[dict] = []
        seen_ids: set[str] = set()

        # L0: policy decisions with verdict != allow.
        violations: dict[str, ActionRecord] = {}
        for rec in action_log:
            if rec.action_type != ActionType.POLICY_DECISION:
                continue
            verdict = rec.payload.get("verdict")
            if verdict in ("rewrite", "block"):
                violations[rec.action_id] = rec
                if rec.action_id not in seen_ids:
                    nodes.append(
                        {"id": rec.action_id, "label": "L0", "agent_id": rec.agent_id}
                    )
                    seen_ids.add(rec.action_id)

        if not violations:
            return {"nodes": nodes, "edges": edges}

        # Reverse index: parent_id -> [children that cite parent_id as a source]
        reverse: dict[str, list[ActionRecord]] = {}
        for rec in action_log:
            for src in rec.source_action_ids:
                reverse.setdefault(src, []).append(rec)
            # MSWM-derived edges: if this action mentions an item the sender
            # previously LEARNED from someone, that learning event is a
            # causal parent.
            if mswm is not None:
                for parent_rec in _mswm_parents(rec, mswm, action_log):
                    reverse.setdefault(parent_rec.action_id, []).append(rec)

        # BFS from the L0 set over the reverse index.
        descendants: set[str] = set()
        frontier: set[str] = set(violations.keys())
        while frontier:
            nxt: set[str] = set()
            for parent in frontier:
                for child in reverse.get(parent, []):
                    if child.action_id in violations:
                        continue
                    if child.action_id in descendants:
                        edges.append(
                            {"src": parent, "dst": child.action_id, "label": "L1"}
                        )
                        continue
                    descendants.add(child.action_id)
                    nxt.add(child.action_id)
                    if child.action_id not in seen_ids:
                        nodes.append(
                            {
                                "id": child.action_id,
                                "label": "L1",
                                "agent_id": child.agent_id,
                            }
                        )
                        seen_ids.add(child.action_id)
                    edges.append(
                        {"src": parent, "dst": child.action_id, "label": "L1"}
                    )
            frontier = nxt

        return {"nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------
    # Proximity fallback (legacy / backward compat)
    # ------------------------------------------------------------------
    def _build_proximity(self, action_log: list[ActionRecord]) -> dict:
        nodes: list[dict] = []
        edges: list[dict] = []
        seen_ids: set[str] = set()

        violations: list[tuple[int, ActionRecord]] = []
        for idx, rec in enumerate(action_log):
            if rec.action_type != ActionType.POLICY_DECISION:
                continue
            verdict = rec.payload.get("verdict")
            if verdict in ("rewrite", "block"):
                violations.append((idx, rec))
                if rec.action_id not in seen_ids:
                    nodes.append(
                        {"id": rec.action_id, "label": "L0", "agent_id": rec.agent_id}
                    )
                    seen_ids.add(rec.action_id)

        for v_idx, v_rec in violations:
            for offset in range(1, self.cascade_window + 1):
                j = v_idx + offset
                if j >= len(action_log):
                    break
                cand = action_log[j]
                if cand.action_type != ActionType.OUTBOUND_MESSAGE:
                    continue
                if cand.action_id not in seen_ids:
                    nodes.append(
                        {
                            "id": cand.action_id,
                            "label": "L1",
                            "agent_id": cand.agent_id,
                        }
                    )
                    seen_ids.add(cand.action_id)
                edges.append(
                    {"src": v_rec.action_id, "dst": cand.action_id, "label": "L1"}
                )

        return {"nodes": nodes, "edges": edges}


def _mswm_has_links(mswm: MSWM) -> bool:
    for peers in mswm.state.values():
        for peer in peers.values():
            if peer.items_learned_from_j or peer.items_told_to_j:
                return True
    return False


def _mswm_parents(
    rec: ActionRecord, mswm: MSWM, action_log: list[ActionRecord]
) -> Iterable[ActionRecord]:
    """Yield ActionRecords from ``action_log`` that are MSWM parents of ``rec``.

    Definition: if ``rec`` is an outbound or memory-side action that carries
    ``mentioned_items``, and the agent's MSWM peer models show the same
    item was LEARNED from some peer via action_id X, then X is a causal
    parent. This lets the builder walk the spec §2.6 chain (C's action
    references z -> B's summary taught C about z -> A disclosed z to B).

    Only items the CURRENT action mentions are considered; unrelated MSWM
    state does not contaminate the attribution.
    """

    if rec.action_type not in (
        ActionType.OUTBOUND_MESSAGE,
        ActionType.MEMORY_WRITE,
        ActionType.SUMMARY_WRITE,
        ActionType.MEMORY_COMPRESSION,
    ):
        return []
    mentioned = rec.payload.get("mentioned_items") or []
    if not mentioned:
        return []

    agent_id = rec.agent_id
    peers = mswm.state.get(agent_id, {})
    by_id = {r.action_id: r for r in action_log}
    parents: list[ActionRecord] = []
    for peer_model in peers.values():
        for item_id, learned_from_action_id in peer_model.items_learned_from_j:
            if item_id in mentioned and learned_from_action_id in by_id:
                parent = by_id[learned_from_action_id]
                if parent.action_id != rec.action_id:
                    parents.append(parent)
    return parents
