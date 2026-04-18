"""Phase F.5 Fix 2: attribution preserves pre-rewrite causal chain.

Under an ENFORCE rewrite the persisted target record's
``mentioned_items`` is the REDUCED list (the forbidden item was redacted
by the policy hook). The policy_decision payload still carries the
ORIGINAL pre-rewrite list plus a post-rewrite copy under
``rewritten_mentioned_items``.

Before Fix 2, :class:`AttributionGraphBuilder._build_causal` seeded the
backward walk with the target's payload list alone, so any ancestor that
propagated only through the forbidden item was orphaned from the DAG.
After Fix 2 the builder prefers the policy_decision's ORIGINAL list when
the rewrite materially changed ``mentioned_items`` and tags the L0 node
with ``rewritten=True`` so downstream consumers can distinguish a
redacted target from a pristine one.

Tests:

1. A three-actor rewrite trace where the forbidden item is the ONLY
   causal bridge to the upstream disclosure. Without Fix 2 the backward
   walk collapses; with Fix 2 the upstream actor appears in the DAG.
2. The L0 node carries the ``rewritten`` annotation when the policy
   payload's original list differs from the persisted one.
3. A non-rewrite policy (verdict=allow) does not trigger the Fix 2 path
   and the target node is NOT annotated.
4. The annotation edge from target to policy_decision is preserved per
   Phase C.5's design.
"""

from __future__ import annotations

from clawsocialarena.audit.attribution import AttributionGraphBuilder
from clawsocialarena.audit.mswm import MSWM
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


def _outbound(
    action_id: str,
    sender: str,
    recipient: str,
    mentioned: list[str],
    *,
    sources: list[str] | None = None,
) -> ActionRecord:
    return ActionRecord(
        action_id=action_id,
        prev_hash="0" * 64,
        agent_id=sender,
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-17T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCLOSURE,
        payload={
            "recipient_id": recipient,
            "content": "msg",
            "mentioned_items": list(mentioned),
        },
        integrity_level=IntegrityLevel.HASH_CHAINED,
        source_action_ids=list(sources or []),
    )


def _rewrite_policy_decision(
    action_id: str,
    agent: str,
    target: str,
    recipient: str,
    original_items: list[str],
    rewritten_items: list[str],
    source_action_ids: list[str],
) -> ActionRecord:
    return ActionRecord(
        action_id=action_id,
        prev_hash="0" * 64,
        agent_id=agent,
        action_type=ActionType.POLICY_DECISION,
        timestamp="2026-04-17T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCLOSURE,
        payload={
            "verdict": "rewrite",
            "policy_id": "rewrite-forbidden",
            "reason": "redact forbidden_item",
            "target_action_id": target,
            "recipient_id": recipient,
            "mentioned_items": list(original_items),
            "rewritten_mentioned_items": list(rewritten_items),
            "source_action_ids": list(source_action_ids),
        },
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def test_rewrite_preserves_upstream_chain_via_policy_payload() -> None:
    """Three-actor ENFORCE rewrite: the forbidden item is the only bridge
    to Alice's upstream disclosure. Without Fix 2, Alice is orphaned in
    the DAG; with Fix 2, the backward walk finds her via the policy's
    original mentioned_items list.

    Trace:
        a1  alice -> bob   mentions [forbidden_item]
        b1  bob   -> carol mentions [forbidden_item] (sources=[a1])
        t1  bob   -> carol mentions [forbidden_item, ok_item]
                             post-rewrite: [ok_item]
                             (sources=[b1])
        p1  policy_decision verdict=rewrite targeting t1
            policy.payload.mentioned_items=[forbidden_item, ok_item]
            policy.payload.rewritten_mentioned_items=[ok_item]

    ``ok_item`` was invented by bob on the t1 disclosure — it has no
    upstream learning event, so the backward walk via MSWM finds
    nothing through it. Only ``forbidden_item`` bridges back to bob's
    earlier actions and then to alice. With the rewritten target's
    mentioned_items = [ok_item] alone, the backward walk fails to reach
    a1.
    """

    a1 = _outbound("a1", "alice", "bob", ["forbidden_item"])
    b1 = _outbound("b1", "bob", "carol", ["forbidden_item"], sources=["a1"])
    # t1's PERSISTED mentioned_items is the rewritten list (post-hook).
    t1 = _outbound(
        "t1",
        "bob",
        "carol",
        ["ok_item"],  # <-- rewritten list
        sources=[],  # Deliberately drop explicit sources to isolate the
                    # MSWM-via-mentioned_items backward walk.
    )
    p1 = _rewrite_policy_decision(
        "p1",
        agent="bob",
        target="t1",
        recipient="carol",
        original_items=["forbidden_item", "ok_item"],
        rewritten_items=["ok_item"],
        source_action_ids=["b1"],  # The rewrite preserved b1 as source.
    )

    log = [a1, b1, t1, p1]
    mswm = MSWM()
    # Note: we apply actions in order to build a realistic MSWM. t1's
    # MSWM update reflects the PERSISTED payload (post-rewrite), since
    # that is what the Session actually commits.
    for rec in log:
        mswm.on_action(rec)

    dag = AttributionGraphBuilder(action_log=log, mswm=mswm).build()
    node_ids = {n["id"] for n in dag["nodes"]}

    # L0 target must be present.
    assert "t1" in node_ids
    # Policy decision is attached as annotation edge.
    edges = {(e["src"], e["dst"], e["label"]) for e in dag["edges"]}
    assert ("t1", "p1", "policy") in edges, (
        "Phase C.5 annotation edge from target to policy_decision must "
        "be preserved"
    )
    # Core Fix 2 assertion: the upstream b1 (and further a1) are in the
    # DAG because the builder used the policy's original mentioned_items
    # to seed the backward walk. Without Fix 2, b1 would be MISSING
    # because t1.payload.mentioned_items = [ok_item] and ok_item has no
    # MSWM trail back to bob.
    assert "b1" in node_ids, (
        "b1 must appear as a causal ancestor via forbidden_item chain"
    )
    assert "a1" in node_ids, (
        "a1 must appear as a two-hop ancestor via forbidden_item chain"
    )


def test_rewritten_flag_on_l0_node_when_mentioned_items_differ() -> None:
    """L0 node carries ``rewritten=True`` when the rewrite materially
    changed the mentioned_items set. Downstream consumers can use this
    to distinguish redacted from pristine targets.
    """

    a1 = _outbound("a1", "alice", "bob", ["forbidden_item"])
    t1 = _outbound("t1", "bob", "carol", ["ok_item"], sources=["a1"])
    p1 = _rewrite_policy_decision(
        "p1",
        agent="bob",
        target="t1",
        recipient="carol",
        original_items=["forbidden_item", "ok_item"],
        rewritten_items=["ok_item"],
        source_action_ids=["a1"],
    )

    log = [a1, t1, p1]
    mswm = MSWM()
    for rec in log:
        mswm.on_action(rec)

    dag = AttributionGraphBuilder(action_log=log, mswm=mswm).build()
    t1_nodes = [n for n in dag["nodes"] if n["id"] == "t1"]
    assert len(t1_nodes) == 1
    assert t1_nodes[0].get("rewritten") is True


def test_pristine_rewrite_without_mentioned_item_change_not_annotated() -> None:
    """A rewrite that only mutated ``content`` (not mentioned_items) does
    NOT trigger the Fix 2 annotation. The L0 node stays pristine because
    the backward walk can use the persisted mentioned_items as-is.
    """

    a1 = _outbound("a1", "alice", "bob", ["item-x"])
    t1 = _outbound("t1", "bob", "carol", ["item-x"], sources=["a1"])
    p1 = _rewrite_policy_decision(
        "p1",
        agent="bob",
        target="t1",
        recipient="carol",
        # Both original and rewritten carry ["item-x"] -> no drop.
        original_items=["item-x"],
        rewritten_items=["item-x"],
        source_action_ids=["a1"],
    )

    log = [a1, t1, p1]
    mswm = MSWM()
    for rec in log:
        mswm.on_action(rec)

    dag = AttributionGraphBuilder(action_log=log, mswm=mswm).build()
    t1_node = next(n for n in dag["nodes"] if n["id"] == "t1")
    # The Fix 2 annotation only fires when original != persisted.
    assert "rewritten" not in t1_node


def test_dag_matches_ground_truth_under_rewrite() -> None:
    """End-to-end: produced DAG under an ENFORCE rewrite matches a
    hand-built GT DAG that encodes the full pre-rewrite causal chain.

    We compare node-id sets and edge triples to a tight hand-specified
    GT, not by a fuzzy F1 threshold, because the builder is
    deterministic and the fixture is small. The assertion doubles as a
    regression canary if Fix 2 ever regresses.
    """

    a1 = _outbound("a1", "alice", "bob", ["forbidden_item"])
    b1 = _outbound("b1", "bob", "carol", ["forbidden_item"], sources=["a1"])
    t1 = _outbound("t1", "bob", "carol", ["ok_item"], sources=[])
    p1 = _rewrite_policy_decision(
        "p1",
        agent="bob",
        target="t1",
        recipient="carol",
        original_items=["forbidden_item", "ok_item"],
        rewritten_items=["ok_item"],
        source_action_ids=["b1"],
    )

    log = [a1, b1, t1, p1]
    mswm = MSWM()
    for rec in log:
        mswm.on_action(rec)

    dag = AttributionGraphBuilder(action_log=log, mswm=mswm).build()
    node_ids = {n["id"] for n in dag["nodes"]}
    # Hand-built GT: expect the target, policy, both upstream actions
    # (a1 and b1) in the node set.
    expected_nodes = {"t1", "p1", "b1", "a1"}
    assert node_ids == expected_nodes

    edge_triples = {(e["src"], e["dst"], e["label"]) for e in dag["edges"]}
    # Core causal chain must be present. The exact L1 edges are:
    #  - t1 -> b1 via policy.source_action_ids + MSWM (b1 is how bob
    #    knows forbidden_item's causal chain)
    #  - b1 -> a1 via explicit source_action_ids
    #  - t1 -> p1 via policy annotation
    assert ("t1", "p1", "policy") in edge_triples
    assert ("t1", "b1", "L1") in edge_triples
    assert ("b1", "a1", "L1") in edge_triples
