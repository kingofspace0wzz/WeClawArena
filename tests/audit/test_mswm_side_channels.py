"""Tests for MSWM side-channel update rules (Phase C / Task C3).

Side-channel actions (memory_write, summary_write, memory_compression,
retrieval_fetch) update the agent's own knowledge bag (``self_knowledge``)
without broadcasting anything to peer models. The decision to use a separate
``self_knowledge: dict[agent_id, set[item_id]]`` container (rather than
encoding self-knowledge via ``MSWM[i][i]``) is documented in ``mswm.py``.
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


def _record(
    action_id: str,
    agent: str,
    action_type: ActionType,
    payload: dict,
) -> ActionRecord:
    return ActionRecord(
        action_id=action_id,
        prev_hash="0" * 64,
        agent_id=agent,
        action_type=action_type,
        timestamp="2026-04-17T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload=payload,
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def test_memory_write_updates_self_knowledge_only() -> None:
    mswm = MSWM()
    mswm.on_action(
        _record(
            "mem-1",
            "alice",
            ActionType.MEMORY_WRITE,
            {"content": "note", "tags": [], "mentioned_items": ["z"]},
        )
    )
    assert mswm.self_knowledge.get("alice") == {"z"}
    # No peer model created — memory writes do not reach peers.
    assert list(mswm.pairs()) == []


def test_summary_write_updates_self_knowledge() -> None:
    mswm = MSWM()
    mswm.on_action(
        _record(
            "sum-1",
            "bob",
            ActionType.SUMMARY_WRITE,
            {"content": "summary", "mentioned_items": ["x", "y"]},
        )
    )
    assert mswm.self_knowledge.get("bob") == {"x", "y"}
    assert list(mswm.pairs()) == []


def test_memory_compression_updates_self_knowledge() -> None:
    mswm = MSWM()
    mswm.on_action(
        _record(
            "mc-1",
            "carol",
            ActionType.MEMORY_COMPRESSION,
            {"content": "compressed", "mentioned_items": ["p"]},
        )
    )
    assert mswm.self_knowledge.get("carol") == {"p"}


def test_retrieval_fetch_with_items_exposed_updates_self_only() -> None:
    mswm = MSWM()
    mswm.on_action(
        _record(
            "rf-1",
            "alice",
            ActionType.RETRIEVAL_FETCH,
            {"items_exposed": ["z", "w"]},
        )
    )
    assert mswm.self_knowledge.get("alice") == {"z", "w"}
    # Retrieval must NOT broadcast to peers.
    assert list(mswm.pairs()) == []


def test_retrieval_fetch_without_items_exposed_is_noop() -> None:
    mswm = MSWM()
    mswm.on_action(
        _record("rf-1", "alice", ActionType.RETRIEVAL_FETCH, {"query": "..."})
    )
    assert mswm.self_knowledge == {}


def test_memory_write_without_mentioned_items_is_noop() -> None:
    mswm = MSWM()
    mswm.on_action(
        _record("mem-1", "alice", ActionType.MEMORY_WRITE, {"content": "note"})
    )
    assert mswm.self_knowledge == {}


def test_self_knowledge_accumulates_across_channels() -> None:
    mswm = MSWM()
    mswm.on_action(
        _record(
            "mem-1", "alice", ActionType.MEMORY_WRITE, {"mentioned_items": ["a"]}
        )
    )
    mswm.on_action(
        _record(
            "rf-1",
            "alice",
            ActionType.RETRIEVAL_FETCH,
            {"items_exposed": ["b"]},
        )
    )
    assert mswm.self_knowledge["alice"] == {"a", "b"}
