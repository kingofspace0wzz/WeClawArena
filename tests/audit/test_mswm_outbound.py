"""Tests for MSWM.on_action outbound-message dispatch (Phase C / Task C2)."""

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
    action_id: str,
    sender: str,
    recipient: str,
    *,
    mentioned: list[str] | None = None,
    content: str = "hello",
    social_phase: SocialPhase = SocialPhase.DISCLOSURE,
) -> ActionRecord:
    payload: dict = {"recipient_id": recipient, "content": content}
    if mentioned is not None:
        payload["mentioned_items"] = mentioned
    return ActionRecord(
        action_id=action_id,
        prev_hash="0" * 64,
        agent_id=sender,
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-17T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=social_phase,
        payload=payload,
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def test_outbound_with_mentioned_items_updates_both_sides() -> None:
    mswm = MSWM()
    action = _outbound("act-1", "alice", "bob", mentioned=["z"])
    mswm.on_action(action)

    sender_peer = mswm.get("alice", "bob")
    recipient_peer = mswm.get("bob", "alice")
    assert ("z", "act-1") in sender_peer.items_told_to_j
    assert ("z", "act-1") in recipient_peer.items_learned_from_j
    assert sender_peer.phase_of_last_interaction == SocialPhase.DISCLOSURE
    assert recipient_peer.phase_of_last_interaction == SocialPhase.DISCLOSURE


def test_outbound_without_mentioned_items_is_noop() -> None:
    """Backward compat: payloads lacking ``mentioned_items`` leave MSWM empty."""
    mswm = MSWM()
    mswm.on_action(_outbound("act-1", "alice", "bob"))
    assert list(mswm.pairs()) == []


def test_outbound_empty_mentioned_items_is_noop() -> None:
    mswm = MSWM()
    mswm.on_action(_outbound("act-1", "alice", "bob", mentioned=[]))
    assert list(mswm.pairs()) == []


def test_multiple_mentioned_items_all_recorded() -> None:
    mswm = MSWM()
    mswm.on_action(_outbound("act-1", "alice", "bob", mentioned=["x", "y", "z"]))
    sender = mswm.get("alice", "bob")
    assert sender.items_told_to_j == {("x", "act-1"), ("y", "act-1"), ("z", "act-1")}


def test_two_sequential_messages_accumulate() -> None:
    mswm = MSWM()
    mswm.on_action(_outbound("act-1", "alice", "bob", mentioned=["x"]))
    mswm.on_action(_outbound("act-2", "alice", "bob", mentioned=["y"]))
    sender = mswm.get("alice", "bob")
    recipient = mswm.get("bob", "alice")
    assert sender.items_told_to_j == {("x", "act-1"), ("y", "act-2")}
    assert recipient.items_learned_from_j == {("x", "act-1"), ("y", "act-2")}


def test_non_string_mentioned_items_are_skipped() -> None:
    mswm = MSWM()
    mswm.on_action(_outbound("act-1", "alice", "bob", mentioned=["x", 42]))  # type: ignore[list-item]
    sender = mswm.get("alice", "bob")
    assert sender.items_told_to_j == {("x", "act-1")}


def test_non_outbound_action_does_nothing() -> None:
    mswm = MSWM()
    llm = ActionRecord(
        action_id="llm-1",
        prev_hash="0" * 64,
        agent_id="alice",
        action_type=ActionType.LLM_CALL,
        timestamp="2026-04-17T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={"input_tokens": 1, "output_tokens": 1, "latency_ms": 1, "model": "x"},
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )
    mswm.on_action(llm)
    assert list(mswm.pairs()) == []
