"""Tests for DAG node labels L0 / L1 / LX / LR / LF (Phase C / Task C9).

Fix-2 rooting semantics: the L0 node is the policy_decision's
``target_action_id``, and the DAG walks BACKWARD to ancestors. L1 / LX /
LR / LF therefore label ancestor nodes — the action that caused the
forbidden inference, the cascade disclosure, the repair retraction, or
the forgotten outbound.
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


def test_policy_violation_target_gets_l0_label() -> None:
    """The policy_decision's target action is the L0 node (Fix-2 rooting).

    The old builder treated the policy_decision row itself as L0; Fix 2
    roots at the target so causal chains can walk backward from the
    offending action.
    """

    target = _outbound("m1", "alice", "bob", mentioned=["z"])
    log = [target, _policy("pol", "alice", target="m1")]
    dag = AttributionGraphBuilder(action_log=log).build()
    assert _label_of(dag, "m1") == "L0"


def test_ancestor_via_source_action_ids_gets_l1_label() -> None:
    """An ancestor cited by source_action_ids gets the default L1 label."""

    ancestor = _outbound("parent", "alice", "bob", mentioned=["z"])
    target = _outbound(
        "target",
        "alice",
        "bob",
        mentioned=["z"],
        sources=["parent"],
    )
    pol = _policy("pol", "alice", target="target")
    log = [ancestor, target, pol]
    dag = AttributionGraphBuilder(action_log=log).build()
    # target is L0; parent is an L1 ancestor.
    assert _label_of(dag, "target") == "L0"
    assert _label_of(dag, "parent") == "L1"


def test_cascaded_ancestor_gets_lx_label() -> None:
    """Same sender's older disclosure to a different peer → LX on the ancestor.

    Alice disclosed z to bob, then alice disclosed z to carol (cascade).
    Policy fires on alice's carol disclosure. Walking backward cites
    alice's earlier bob disclosure as the ancestor — that ancestor's
    recipient differs from the target's recipient, so it gets LX.
    """

    parent = _outbound("parent", "alice", "bob", mentioned=["z"])
    target = _outbound(
        "target",
        "alice",
        "carol",
        mentioned=["z"],
        sources=["parent"],
    )
    pol = _policy("pol", "alice", target="target")
    log = [parent, target, pol]

    mswm = MSWM()
    for rec in log:
        mswm.on_action(rec)

    dag = AttributionGraphBuilder(action_log=log, mswm=mswm).build()
    assert _label_of(dag, "parent") == "LX"


def test_repair_ancestor_gets_lr_label() -> None:
    """An ancestor marked as a repair of an even earlier action gets LR."""

    original = _outbound("original", "alice", "bob", mentioned=["z"])
    repair = _outbound(
        "repair",
        "alice",
        "bob",
        mentioned=["z"],
        sources=["original"],
        repair_of="original",
    )
    target = _outbound(
        "target",
        "alice",
        "bob",
        mentioned=["z"],
        sources=["repair"],
    )
    pol = _policy("pol", "alice", target="target")
    log = [original, repair, target, pol]
    mswm = MSWM()
    for rec in log:
        mswm.on_action(rec)
    dag = AttributionGraphBuilder(action_log=log, mswm=mswm).build()
    assert _label_of(dag, "repair") == "LR"


def test_forgotten_outbound_gets_lf_label() -> None:
    """Outbound whose MSWM tuples were reverted (e.g. a block) → LF.

    The forgotten action is not part of the policy's target chain; it is
    a separate outbound whose MSWM footprint was cleared. It still ends
    up in the DAG as an LF orphan so analysts can see the block.
    """

    # Build a minimal scenario where some action 'blocked' was blocked
    # and another policy_decision targets a real outbound 'target'.
    target = _outbound("target", "alice", "bob", mentioned=["z"])
    blocked = _outbound("blocked", "alice", "carol", mentioned=["z"])
    pol = _policy("pol", "alice", target="target")
    log = [target, blocked, pol]

    mswm = MSWM()
    mswm.on_action(target)
    mswm.on_action(blocked)
    mswm.revert_action(blocked)  # Block causes MSWM revert.

    dag = AttributionGraphBuilder(action_log=log, mswm=mswm).build()
    # blocked is orphaned (not cited by anything) but its mswm footprint
    # is gone → LF.
    assert _label_of(dag, "blocked") == "LF"


def test_lr_takes_precedence_over_lx_on_ancestor() -> None:
    """When an ancestor has both a repair marker and a cascade, LR wins."""

    # alice's earlier disclosure to bob is the original.
    original = _outbound("original", "alice", "bob", mentioned=["z"])
    # alice's repair (to a new peer carol + repair_of marker) is the
    # ancestor of the target.
    repair = _outbound(
        "repair",
        "alice",
        "carol",
        mentioned=["z"],
        sources=["original"],
        repair_of="original",
    )
    target = _outbound(
        "target",
        "alice",
        "carol",
        mentioned=["z"],
        sources=["repair"],
    )
    pol = _policy("pol", "alice", target="target")
    log = [original, repair, target, pol]
    mswm = MSWM()
    for rec in log:
        mswm.on_action(rec)
    dag = AttributionGraphBuilder(action_log=log, mswm=mswm).build()
    # repair matches both LR (has repair_of) and LX (new recipient carol
    # vs old bob). LR wins.
    assert _label_of(dag, "repair") == "LR"
