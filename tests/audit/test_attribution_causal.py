"""Tests for MSWM-aware causal attribution edges (Phase C / Task C7).

The Phase C attribution builder takes an action_log plus an MSWM. Causal
parents come from both explicit ``source_action_ids`` and MSWM
``items_learned_from_j`` back-references. This file exercises the MSWM
path specifically — the spec §2.6 two-hop example: A discloses z to B at
turn 3; B summarises z and C reads the summary (retrieval); C acts on z
at turn 9. MSWM alone should chain these across two hops.
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
    mentioned: list[str] | None = None,
    *,
    sources: list[str] | None = None,
) -> ActionRecord:
    payload: dict = {"recipient_id": recipient, "content": "."}
    if mentioned is not None:
        payload["mentioned_items"] = mentioned
    return ActionRecord(
        action_id=action_id,
        prev_hash="0" * 64,
        agent_id=sender,
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-17T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCLOSURE,
        payload=payload,
        integrity_level=IntegrityLevel.HASH_CHAINED,
        source_action_ids=list(sources or []),
    )


def _policy_decision(action_id: str, agent: str, target: str) -> ActionRecord:
    return ActionRecord(
        action_id=action_id,
        prev_hash="0" * 64,
        agent_id=agent,
        action_type=ActionType.POLICY_DECISION,
        timestamp="2026-04-17T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCLOSURE,
        payload={"verdict": "block", "policy_id": "p", "target_action_id": target},
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def test_mswm_two_hop_chain_adds_causal_edges() -> None:
    """A→B (turn 3) then B→C (turn 6) then C violates policy on turn 9.

    Fix-2 rooting walks BACKWARD from C's outbound (the target) via MSWM:
    C learned ``z`` from bob's turn-6 disclosure, and bob learned ``z``
    from alice's turn-3 disclosure. Both should appear in the DAG as L1
    ancestors of the L0 target.
    """

    a_to_b = _outbound("a1", "alice", "bob", ["z"])
    b_to_c = _outbound("b1", "bob", "carol", ["z"])
    c_out = _outbound("c1", "carol", "dave", ["z"])
    pol = _policy_decision("p1", "carol", target="c1")

    log = [a_to_b, b_to_c, c_out, pol]
    mswm = MSWM()
    for rec in log:
        mswm.on_action(rec)

    dag = AttributionGraphBuilder(action_log=log, mswm=mswm).build()
    node_ids = {n["id"] for n in dag["nodes"]}
    assert "c1" in node_ids  # L0 target
    assert "b1" in node_ids  # Direct MSWM parent of c1
    assert "a1" in node_ids  # MSWM grandparent
    # Annotation edge target → policy_decision.
    edge_triples = {(e["src"], e["dst"], e["label"]) for e in dag["edges"]}
    assert ("c1", "p1", "policy") in edge_triples


def test_mswm_back_reference_creates_causal_edge_to_learning_action() -> None:
    """Target's MSWM ``items_learned_from_j`` points at the learning action."""

    # Alice tells Bob about item z. Bob's downstream outbound is the
    # target of a policy decision.
    a_to_b = _outbound("a-tell", "alice", "bob", ["z"])
    b_act = _outbound("b-act", "bob", "carol", ["z"], sources=["a-tell"])
    pol = _policy_decision("pol-1", "bob", target="b-act")

    log = [a_to_b, b_act, pol]
    mswm = MSWM()
    for rec in log:
        mswm.on_action(rec)

    dag = AttributionGraphBuilder(action_log=log, mswm=mswm).build()
    ids = {n["id"] for n in dag["nodes"]}
    assert "b-act" in ids  # L0
    assert "a-tell" in ids  # L1 ancestor via source_action_ids
    edges = {(e["src"], e["dst"], e["label"]) for e in dag["edges"]}
    assert ("b-act", "a-tell", "L1") in edges


def test_two_hop_mswm_chain_via_message_items() -> None:
    """Two-hop MSWM chain: A1 → B1 → target via item z (no explicit sources)."""

    a_to_b = _outbound("A1", "alice", "bob", ["z"])
    b_to_c = _outbound("B1", "bob", "carol", ["z"])
    target = _outbound("target", "carol", "dave", ["z"])  # No sources, only MSWM
    pol = _policy_decision("pol", "carol", target="target")
    log = [a_to_b, b_to_c, target, pol]

    mswm = MSWM()
    for rec in log:
        mswm.on_action(rec)

    dag = AttributionGraphBuilder(action_log=log, mswm=mswm).build()
    edge_triples = {(e["src"], e["dst"], e["label"]) for e in dag["edges"]}
    # target → B1 via MSWM (carol learned z from bob).
    assert ("target", "B1", "L1") in edge_triples
    # B1 → A1 via MSWM (bob learned z from alice).
    assert ("B1", "A1", "L1") in edge_triples


def test_mswm_not_supplied_rebuilds_from_log() -> None:
    """When MSWM is absent, the builder replays the log to rebuild MSWM."""

    a_to_b = _outbound("a1", "alice", "bob", ["z"])
    b_to_c = _outbound("b1", "bob", "carol", ["z"])
    pol = _policy_decision("pol", "bob", target="b1")
    log = [a_to_b, b_to_c, pol]

    # No MSWM passed — builder must internally replay the log.
    dag = AttributionGraphBuilder(action_log=log).build()
    ids = {n["id"] for n in dag["nodes"]}
    assert "b1" in ids  # L0 target
    assert "a1" in ids  # L1 ancestor (MSWM-derived)


def test_legacy_constructor_still_works() -> None:
    """Old idiom ``AttributionGraphBuilder().build(action_log=log)`` works."""

    msg = _outbound("m1", "alice", "bob", ["z"])
    pol = _policy_decision("pol", "alice", target="m1")
    log = [msg, pol]
    dag = AttributionGraphBuilder().build(action_log=log)
    ids = {n["id"] for n in dag["nodes"]}
    assert "m1" in ids  # L0 target
    assert "pol" in ids  # policy annotation node


def test_blocked_target_uses_policy_payload_for_rooting() -> None:
    """A blocked action has no ActionRecord; Fix-2 reconstructs from the
    policy_decision payload (recipient_id, mentioned_items, source_action_ids).
    """

    # Alice discloses z to bob; bob has item z in MSWM.
    a_to_b = _outbound("a1", "alice", "bob", ["z"])
    # The policy_decision carries the blocked action's context. There is
    # no OUTBOUND_MESSAGE row for the blocked action itself.
    pol = ActionRecord(
        action_id="pol-block",
        prev_hash="0" * 64,
        agent_id="bob",
        action_type=ActionType.POLICY_DECISION,
        timestamp="2026-04-17T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCLOSURE,
        payload={
            "verdict": "block",
            "policy_id": "p",
            "target_action_id": "blocked-target",
            "recipient_id": "carol",
            "mentioned_items": ["z"],
            "source_action_ids": ["a1"],
        },
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )
    log = [a_to_b, pol]
    mswm = MSWM()
    for rec in log:
        mswm.on_action(rec)

    dag = AttributionGraphBuilder(action_log=log, mswm=mswm).build()
    ids = {n["id"] for n in dag["nodes"]}
    # The target is synthetic (no record in the log) but still gets an
    # L0 node so consumers can navigate.
    assert "blocked-target" in ids
    assert "a1" in ids  # L1 ancestor via source_action_ids on the policy
    edges = {(e["src"], e["dst"], e["label"]) for e in dag["edges"]}
    assert ("blocked-target", "a1", "L1") in edges
