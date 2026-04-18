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


def test_predicate_decidable_before_any_disclosure() -> None:
    mswm = MSWM()
    predicate = {
        "type": "must_not_decide",
        "for_agent": "carol",
        "forbidden_inference": ["med_x", "condition_y"],
    }
    assert mswm.joint_decidability("alice", predicate) == "decidable"


def test_predicate_still_decidable_after_one_of_two_items_known() -> None:
    """A tells C med_x. C still can't form the joint inference — decidable."""
    mswm = MSWM()
    mswm.on_action(_outbound("act-1", "alice", "carol", ["med_x"]))
    predicate = {
        "type": "must_not_decide",
        "for_agent": "carol",
        "forbidden_inference": ["med_x", "condition_y"],
    }
    assert mswm.joint_decidability("alice", predicate) == "decidable"


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
    # Empty knowledge → violated under must_decide.
    assert mswm.joint_decidability("alice", predicate) == "violated"
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
