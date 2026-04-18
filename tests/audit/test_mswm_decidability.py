"""Tests for MSWM.joint_decidability (Phase C / Task C4).

Backs the spec §3.1 inferential-leakage vignette: A tells C "my friend uses
medication X"; B tells C "my coworker has that condition". Under MSWM, after
both disclosures C's known_items contains {item_X, item_condition}. A policy
declaring "C must not decide {A's friend, B's coworker} are the same person"
(represented as a forbidden_inference over {item_X, item_condition}) should
flip from ``decidable`` (C lacks one item) to ``violated`` after C holds both.
"""

from __future__ import annotations

from clawsocialarena.audit.mswm import MSWM
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


def _outbound(
    action_id: str, sender: str, recipient: str, mentioned: list[str]
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
            "mentioned_items": mentioned,
        },
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def test_predicate_undecidable_before_any_disclosure() -> None:
    """Empty MSWM: target agent has no entries → undecidable, not decidable.

    Previously this returned ``decidable`` because every forbidden item
    was "not in the bag"; but Codex's Phase C review flagged that as
    incorrect — the absence of any evidence about ``for_agent`` means the
    model cannot pin down whether the inference is formable, not that it
    definitely is not.
    """

    mswm = MSWM()
    predicate = {
        "type": "must_not_decide",
        "for_agent": "carol",
        "forbidden_inference": ["med_x", "condition_y"],
    }
    assert mswm.joint_decidability("alice", predicate) == "undecidable"


def test_predicate_decidable_after_one_observed_one_disclosed() -> None:
    """A tells C med_x; dave discloses condition_y to bob (visible in MSWM).

    Now every item has been observed in some channel, and the target
    agent has an MSWM entry. med_x is in carol's bag; condition_y is
    observed on a dave→bob edge but carol does not know it — so the
    joint inference is NOT formable, yielding decidable.
    """

    mswm = MSWM()
    mswm.on_action(_outbound("act-1", "alice", "carol", ["med_x"]))
    # Seed condition_y via an unrelated outbound so "never observed" is
    # not what triggers undecidability.
    mswm.on_action(_outbound("act-seed", "dave", "bob", ["condition_y"]))
    predicate = {
        "type": "must_not_decide",
        "for_agent": "carol",
        "forbidden_inference": ["med_x", "condition_y"],
    }
    assert mswm.joint_decidability("alice", predicate) == "decidable"


def test_predicate_undecidable_when_one_forbidden_item_unseen() -> None:
    """A tells C med_x; condition_y was never observed anywhere → undecidable."""

    mswm = MSWM()
    mswm.on_action(_outbound("act-1", "alice", "carol", ["med_x"]))
    predicate = {
        "type": "must_not_decide",
        "for_agent": "carol",
        "forbidden_inference": ["med_x", "condition_y"],
    }
    assert mswm.joint_decidability("alice", predicate) == "undecidable"


def test_predicate_violated_after_both_items_known_to_target() -> None:
    """A and B both disclose to C — predicate is violated."""
    mswm = MSWM()
    mswm.on_action(_outbound("act-1", "alice", "carol", ["med_x"]))
    mswm.on_action(_outbound("act-2", "bob", "carol", ["condition_y"]))
    predicate = {
        "type": "must_not_decide",
        "for_agent": "carol",
        "forbidden_inference": ["med_x", "condition_y"],
    }
    assert mswm.joint_decidability("alice", predicate) == "violated"


def test_must_decide_inverts_polarity() -> None:
    mswm = MSWM()
    predicate = {
        "type": "must_decide",
        "for_agent": "carol",
        "forbidden_inference": ["med_x", "condition_y"],
    }
    # Empty MSWM: target agent has no entry, items never observed →
    # undecidable under the new semantics (not violated).
    assert mswm.joint_decidability("alice", predicate) == "undecidable"
    mswm.on_action(_outbound("act-1", "alice", "carol", ["med_x"]))
    mswm.on_action(_outbound("act-2", "bob", "carol", ["condition_y"]))
    assert mswm.joint_decidability("alice", predicate) == "decidable"


def test_unknown_predicate_type_is_undecidable() -> None:
    mswm = MSWM()
    predicate = {"type": "unexpected", "forbidden_inference": ["z"]}
    assert mswm.joint_decidability("alice", predicate) == "undecidable"


def test_empty_forbidden_inference_has_clear_semantics() -> None:
    mswm = MSWM()
    predicate = {
        "type": "must_not_decide",
        "for_agent": "carol",
        "forbidden_inference": [],
    }
    # No items to join ⇒ the forbidden inference cannot be formed.
    assert mswm.joint_decidability("alice", predicate) == "decidable"

    must_decide = {
        "type": "must_decide",
        "for_agent": "carol",
        "forbidden_inference": [],
    }
    assert mswm.joint_decidability("alice", must_decide) == "violated"


def test_self_knowledge_counts_towards_derivability() -> None:
    """RETRIEVAL_FETCH self-knowledge should satisfy 'known' for decidability."""
    mswm = MSWM()
    # Carol learns med_x via her own retrieval, not via a peer.
    retrieval = ActionRecord(
        action_id="rf-1",
        prev_hash="0" * 64,
        agent_id="carol",
        action_type=ActionType.RETRIEVAL_FETCH,
        timestamp="2026-04-17T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={"items_exposed": ["med_x"]},
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )
    mswm.on_action(retrieval)
    # Bob tells Carol condition_y.
    mswm.on_action(_outbound("act-b", "bob", "carol", ["condition_y"]))
    predicate = {
        "type": "must_not_decide",
        "for_agent": "carol",
        "forbidden_inference": ["med_x", "condition_y"],
    }
    assert mswm.joint_decidability("alice", predicate) == "violated"


def test_for_agent_falls_back_to_agent_id_when_absent() -> None:
    """Backward-compat: omit for_agent and the subject is agent_id."""
    mswm = MSWM()
    mswm.on_action(_outbound("act-1", "alice", "carol", ["med_x"]))
    mswm.on_action(_outbound("act-2", "bob", "carol", ["condition_y"]))
    predicate = {
        "type": "must_not_decide",
        "forbidden_inference": ["med_x", "condition_y"],
    }
    assert mswm.joint_decidability("carol", predicate) == "violated"


def test_joint_decidability_returns_undecidable_for_unseen_items() -> None:
    """A forbidden item that has never been observed anywhere → undecidable.

    Even if ``for_agent`` has a non-empty MSWM entry, if at least one
    referenced item has never been seen in any channel the model cannot
    report a confident verdict.
    """

    mswm = MSWM()
    mswm.on_action(_outbound("act-1", "alice", "carol", ["med_x"]))
    # item_unseen has never been in any outbound / self_knowledge / peer
    # channel → undecidable.
    predicate = {
        "type": "must_not_decide",
        "for_agent": "carol",
        "forbidden_inference": ["med_x", "item_unseen"],
    }
    assert mswm.joint_decidability("alice", predicate) == "undecidable"


def test_joint_decidability_returns_undecidable_for_unknown_peer() -> None:
    """A for_agent that has no MSWM entry at all → undecidable.

    Even when every forbidden item has been observed in some channel, if
    the target agent itself has never appeared in any action the model
    cannot rule for or against the inference.
    """

    mswm = MSWM()
    # Alice and Bob both disclose items, but Carol has never appeared.
    mswm.on_action(_outbound("act-1", "alice", "bob", ["med_x"]))
    mswm.on_action(_outbound("act-2", "bob", "alice", ["condition_y"]))
    predicate = {
        "type": "must_not_decide",
        "for_agent": "carol",
        "forbidden_inference": ["med_x", "condition_y"],
    }
    assert mswm.joint_decidability("alice", predicate) == "undecidable"
