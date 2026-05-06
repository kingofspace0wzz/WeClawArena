"""Tests for the MSWM data model (Phase C / Task C1)."""

from __future__ import annotations

from clawsocialarena.audit.mswm import MSWM, MswmTransaction, PeerModel
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
) -> ActionRecord:
    return ActionRecord(
        action_id=action_id,
        prev_hash="0" * 64,
        agent_id=sender,
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-27T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={
            "recipient_id": recipient,
            "content": "hello",
            "mentioned_items": mentioned,
        },
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def test_mswm_instantiates_empty() -> None:
    mswm = MSWM()
    assert mswm.state == {}
    assert list(mswm.pairs()) == []


def test_get_returns_default_peer_model() -> None:
    mswm = MSWM()
    model = mswm.get("alice", "bob")
    assert isinstance(model, PeerModel)
    assert model.items_told_to_j == set()
    assert model.items_learned_from_j == set()
    assert model.commitments_to_j == set()
    assert model.phase_of_last_interaction is None
    assert model.trust_estimate == 0.5


def test_get_is_idempotent_returns_same_instance() -> None:
    mswm = MSWM()
    first = mswm.get("alice", "bob")
    first.items_told_to_j.add(("z", "act-1"))
    second = mswm.get("alice", "bob")
    assert second is first
    assert ("z", "act-1") in second.items_told_to_j


def test_pairs_iterates_present_edges() -> None:
    mswm = MSWM()
    mswm.get("alice", "bob")
    mswm.get("alice", "carol")
    mswm.get("bob", "alice")
    pairs = set(mswm.pairs())
    assert pairs == {("alice", "bob"), ("alice", "carol"), ("bob", "alice")}


def test_peer_model_independent_sets() -> None:
    """Default-factory sets must not be shared across PeerModel instances."""
    mswm = MSWM()
    a = mswm.get("alice", "bob")
    b = mswm.get("alice", "carol")
    a.items_told_to_j.add(("x", "act-1"))
    assert ("x", "act-1") not in b.items_told_to_j


def test_mswm_clone_is_independent() -> None:
    mswm = MSWM()
    mswm.on_action(_outbound("act-1", "alice", "bob", ["z"]))

    cloned = mswm.clone()
    cloned.on_action(_outbound("act-2", "alice", "bob", ["private"]))

    assert mswm.known_items("bob") == {"z"}
    assert cloned.known_items("bob") == {"z", "private"}


def test_mswm_transaction_commit_returns_tentative_state() -> None:
    committed = MSWM()
    committed.on_action(_outbound("act-1", "alice", "bob", ["z"]))
    tx = MswmTransaction(committed)

    tx.apply_candidate(_outbound("act-2", "carol", "bob", ["y"]))

    assert committed.known_items("bob") == {"z"}
    assert tx.tentative.known_items("bob") == {"z", "y"}
    committed_after = tx.commit()
    assert committed_after.known_items("bob") == {"z", "y"}


def test_mswm_transaction_rebuild_and_discard() -> None:
    committed = MSWM()
    committed.on_action(_outbound("act-1", "alice", "bob", ["z"]))
    tx = MswmTransaction(committed)

    tx.apply_candidate(_outbound("act-2", "carol", "bob", ["bad"]))
    tx.rebuild(_outbound("act-2", "carol", "bob", ["safe"]))
    assert tx.tentative.known_items("bob") == {"z", "safe"}

    tx.discard()
    assert committed.known_items("bob") == {"z"}
    assert tx.tentative.known_items("bob") == {"z"}
