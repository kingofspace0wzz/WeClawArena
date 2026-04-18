"""Tests for DAG node labels L0 / L1 / LX / LR / LF (Phase C / Task C9)."""

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
    *,
    mentioned: list[str] | None = None,
    sources: list[str] | None = None,
    repair_of: str | None = None,
) -> ActionRecord:
    payload: dict = {"recipient_id": recipient, "content": "."}
    if mentioned is not None:
        payload["mentioned_items"] = mentioned
    if repair_of is not None:
        payload["repair_of"] = repair_of
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


def _policy(action_id: str, agent: str, target: str, verdict: str = "block") -> ActionRecord:
    return ActionRecord(
        action_id=action_id,
        prev_hash="0" * 64,
        agent_id=agent,
        action_type=ActionType.POLICY_DECISION,
        timestamp="2026-04-17T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={"verdict": verdict, "policy_id": "p", "target_action_id": target},
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def _label_of(dag: dict, node_id: str) -> str:
    for n in dag["nodes"]:
        if n["id"] == node_id:
            return n["label"]
    raise AssertionError(f"node {node_id} not in DAG: {dag}")


def test_policy_violation_gets_l0_label() -> None:
    log = [_policy("pol", "alice", target="m1")]
    dag = AttributionGraphBuilder(action_log=log).build()
    assert _label_of(dag, "pol") == "L0"


def test_descendant_default_is_l1() -> None:
    log = [
        _policy("pol", "alice", target="m1"),
        _outbound("m1", "alice", "bob", mentioned=["z"], sources=["pol"]),
    ]
    dag = AttributionGraphBuilder(action_log=log).build()
    assert _label_of(dag, "m1") == "L1"


def test_cascaded_disclosure_gets_lx_label() -> None:
    """Same sender, same item, new recipient → LX."""
    # Alice tells Bob z; later the L0 fires and Alice's NEW message to Carol
    # mentioning z again is a cascade to a different recipient.
    a_to_b = _outbound("a1", "alice", "bob", mentioned=["z"])
    pol = _policy("pol", "alice", target="a2")
    a_to_c = _outbound(
        "a2", "alice", "carol", mentioned=["z"], sources=["pol"]
    )
    log = [a_to_b, pol, a_to_c]

    mswm = MSWM()
    # Replay to populate items_told_to_j for (alice, bob).
    for rec in log:
        mswm.on_action(rec)

    dag = AttributionGraphBuilder(action_log=log, mswm=mswm).build()
    assert _label_of(dag, "a2") == "LX"


def test_repair_action_gets_lr_label() -> None:
    """An outbound with ``repair_of`` citing an existing action gets LR."""
    original = _outbound("a1", "alice", "bob", mentioned=["z"])
    pol = _policy("pol", "alice", target="a2")
    repair = _outbound(
        "a2",
        "alice",
        "bob",
        mentioned=["z"],
        sources=["pol"],
        repair_of="a1",
    )
    log = [original, pol, repair]
    mswm = MSWM()
    for rec in log:
        mswm.on_action(rec)
    dag = AttributionGraphBuilder(action_log=log, mswm=mswm).build()
    assert _label_of(dag, "a2") == "LR"


def test_forgotten_outbound_gets_lf_label() -> None:
    """Outbound whose MSWM tuples were reverted (e.g. a block) → LF."""

    a1 = _outbound("a1", "alice", "bob", mentioned=["z"])
    blocked = _outbound("a2", "alice", "carol", mentioned=["z"])
    pol = _policy("pol", "alice", target="a2")
    log = [a1, blocked, pol]

    # Build MSWM, then simulate the Session's revert on the blocked action.
    mswm = MSWM()
    mswm.on_action(a1)
    mswm.on_action(blocked)
    mswm.revert_action(blocked)  # Block causes MSWM revert.

    dag = AttributionGraphBuilder(action_log=log, mswm=mswm).build()
    # pol is L0; a2 is orphaned (not cited by anything) but its mswm
    # footprint is gone → LF.
    assert _label_of(dag, "a2") == "LF"


def test_lr_takes_precedence_over_lx() -> None:
    """When both repair and cascade apply, LR wins (explicit repair marker)."""
    a1 = _outbound("a1", "alice", "bob", mentioned=["z"])
    # a2 would be LX (z cascaded to carol) but carries a repair_of marker.
    pol = _policy("pol", "alice", target="a2")
    a2 = _outbound(
        "a2",
        "alice",
        "carol",
        mentioned=["z"],
        sources=["pol"],
        repair_of="a1",
    )
    log = [a1, pol, a2]
    mswm = MSWM()
    for rec in log:
        mswm.on_action(rec)
    dag = AttributionGraphBuilder(action_log=log, mswm=mswm).build()
    assert _label_of(dag, "a2") == "LR"
