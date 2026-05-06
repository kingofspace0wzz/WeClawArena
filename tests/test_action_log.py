import asyncio
import sqlite3

import pytest
from pathlib import Path

from clawsocialarena.action_log import ActionLog, HashChainBroken
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    GovernanceRecord,
    IntegrityLevel,
    ExecutionPhase,
    SocialPhase,
)
from clawsocialarena.hashing import GENESIS_HASH


def _record(agent_id: str, prev_hash: str, payload: dict) -> ActionRecord:
    return ActionRecord(
        action_id=f"{agent_id}-{prev_hash[:6]}",
        prev_hash=prev_hash,
        agent_id=agent_id,
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-15T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload=payload,
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def test_append_and_read(tmp_path: Path):
    log = ActionLog(db_path=tmp_path / "run.db")
    rec = _record("alice", GENESIS_HASH, {"msg": "hi"})
    stored_hash = log.append(rec)
    # Hash now covers the full canonical envelope minus prev_hash + record_hash
    assert len(stored_hash) == 64
    assert stored_hash != GENESIS_HASH

    all_rows = log.read_all()
    assert len(all_rows) == 1
    assert all_rows[0].agent_id == "alice"
    assert all_rows[0].payload == {"msg": "hi"}


def test_per_agent_chain(tmp_path: Path):
    log = ActionLog(db_path=tmp_path / "run.db")
    h1 = log.append(_record("alice", GENESIS_HASH, {"i": 1}))
    h2 = log.append(_record("alice", h1, {"i": 2}))
    # bob starts his own chain (distinct payload so hashes trivially differ)
    h3 = log.append(_record("bob", GENESIS_HASH, {"i": 3}))
    assert h1 != h3
    assert log.head_hash("alice") == h2
    assert log.head_hash("bob") == h3


def test_broken_chain_raises(tmp_path: Path):
    log = ActionLog(db_path=tmp_path / "run.db")
    log.append(_record("alice", GENESIS_HASH, {"i": 1}))
    with pytest.raises(HashChainBroken):
        # prev_hash that doesn't match head -> error
        log.append(_record("alice", "f" * 64, {"i": 2}))


def test_verify_chain_ok(tmp_path: Path):
    log = ActionLog(db_path=tmp_path / "run.db")
    h1 = log.append(_record("alice", GENESIS_HASH, {"i": 1}))
    log.append(_record("alice", h1, {"i": 2}))
    assert log.verify_chain("alice") is True


def test_verify_chain_detects_tamper(tmp_path: Path):
    log = ActionLog(db_path=tmp_path / "run.db")
    h1 = log.append(_record("alice", GENESIS_HASH, {"i": 1}))
    log.append(_record("alice", h1, {"i": 2}))
    # Manually tamper with the payload JSON
    with log.connect() as conn:
        conn.execute(
            "UPDATE actions SET payload_json = ? WHERE agent_id = 'alice' AND prev_hash = ?",
            ('{"i": 999}', GENESIS_HASH),
        )
        conn.commit()
    assert log.verify_chain("alice") is False


def test_tamper_social_phase_detected(tmp_path: Path):
    log = ActionLog(db_path=tmp_path / "run.db")
    h1 = log.append(_record("alice", GENESIS_HASH, {"i": 1}))
    log.append(_record("alice", h1, {"i": 2}))
    with log.connect() as conn:
        conn.execute(
            "UPDATE actions SET social_phase = 'negotiation' WHERE agent_id = 'alice' AND prev_hash = ?",
            (GENESIS_HASH,),
        )
        conn.commit()
    assert log.verify_chain("alice") is False


def test_tamper_integrity_level_detected(tmp_path: Path):
    log = ActionLog(db_path=tmp_path / "run.db")
    h1 = log.append(_record("alice", GENESIS_HASH, {"i": 1}))
    log.append(_record("alice", h1, {"i": 2}))
    with log.connect() as conn:
        conn.execute(
            "UPDATE actions SET integrity_level = 1 WHERE agent_id = 'alice' AND prev_hash = ?",
            (GENESIS_HASH,),
        )
        conn.commit()
    assert log.verify_chain("alice") is False


def test_tamper_record_hash_detected(tmp_path: Path):
    log = ActionLog(db_path=tmp_path / "run.db")
    h1 = log.append(_record("alice", GENESIS_HASH, {"i": 1}))
    log.append(_record("alice", h1, {"i": 2}))
    with log.connect() as conn:
        conn.execute(
            "UPDATE actions SET record_hash = ? WHERE agent_id = 'alice' AND prev_hash = ?",
            ("ff" * 32, GENESIS_HASH),
        )
        conn.commit()
    assert log.verify_chain("alice") is False


def test_tamper_execution_phase_detected(tmp_path: Path):
    log = ActionLog(db_path=tmp_path / "run.db")
    h1 = log.append(_record("alice", GENESIS_HASH, {"i": 1}))
    log.append(_record("alice", h1, {"i": 2}))
    with log.connect() as conn:
        conn.execute(
            "UPDATE actions SET execution_phase = 'retry' WHERE agent_id = 'alice' AND prev_hash = ?",
            (GENESIS_HASH,),
        )
        conn.commit()
    assert log.verify_chain("alice") is False


def test_tamper_timestamp_detected(tmp_path: Path):
    log = ActionLog(db_path=tmp_path / "run.db")
    h1 = log.append(_record("alice", GENESIS_HASH, {"i": 1}))
    log.append(_record("alice", h1, {"i": 2}))
    with log.connect() as conn:
        conn.execute(
            "UPDATE actions SET timestamp = '1999-01-01T00:00:00Z' WHERE agent_id = 'alice' AND prev_hash = ?",
            (GENESIS_HASH,),
        )
        conn.commit()
    assert log.verify_chain("alice") is False


def test_source_action_ids_round_trip(tmp_path: Path):
    """source_action_ids is persisted and restored on read_all."""
    log = ActionLog(db_path=tmp_path / "run.db")
    rec = ActionRecord(
        action_id="alice-a",
        prev_hash=GENESIS_HASH,
        agent_id="alice",
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-15T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={"i": 1},
        integrity_level=IntegrityLevel.HASH_CHAINED,
        source_action_ids=["parent-1", "parent-2"],
    )
    log.append(rec)
    rows = log.read_all()
    assert rows[0].source_action_ids == ["parent-1", "parent-2"]


def test_tamper_source_action_ids_detected(tmp_path: Path):
    """Tampering with source_action_ids in SQL breaks verify_chain (σ/φ)."""
    log = ActionLog(db_path=tmp_path / "run.db")
    rec = ActionRecord(
        action_id="alice-a",
        prev_hash=GENESIS_HASH,
        agent_id="alice",
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-15T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={"i": 1},
        integrity_level=IntegrityLevel.HASH_CHAINED,
        source_action_ids=["parent-1"],
    )
    log.append(rec)
    with log.connect() as conn:
        conn.execute(
            "UPDATE actions SET source_action_ids = ? WHERE action_id = ?",
            ('["evil"]', "alice-a"),
        )
        conn.commit()
    assert log.verify_chain("alice") is False


def test_governance_round_trips_and_is_hash_bound(tmp_path: Path):
    """Tampering with governance_json breaks verify_chain."""
    log = ActionLog(db_path=tmp_path / "run.db")
    rec = _record("alice", GENESIS_HASH, {"i": 1}).model_copy(
        update={
            "governance": GovernanceRecord(
                owner_id="owner-alice",
                active_identity_id="identity-alice",
                authorization_scope_id="scope-calendar",
                approval_mandate_id="mandate-owner",
                escalation_state="approved",
            )
        }
    )

    log.append(rec)
    rows = log.read_all()
    assert rows[0].governance == rec.governance

    with log.connect() as conn:
        conn.execute(
            "UPDATE actions SET governance_json = ? WHERE action_id = ?",
            (
                '{"active_identity_id":"identity-bob","approval_mandate_id":"mandate-owner",'
                '"authorization_scope_id":"scope-calendar","escalation_state":"approved",'
                '"owner_id":"owner-alice"}',
                rec.action_id,
            ),
        )
        conn.commit()
    assert log.verify_chain("alice") is False


def test_unique_constraint_rejects_forked_prev_hash(tmp_path: Path):
    """Schema-level UNIQUE(agent_id, prev_hash) rejects forked inserts at the DB layer."""
    log = ActionLog(db_path=tmp_path / "run.db")
    # First append from GENESIS succeeds, establishing (alice, GENESIS_HASH) as a used pair.
    log.append(_record("alice", GENESIS_HASH, {"i": 1}))
    # A raw second insert citing GENESIS as prev_hash for alice must trip UNIQUE.
    # (This bypasses the HashChainBroken check to verify the constraint itself.)
    with log.connect() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO actions
                (agent_id, action_id, prev_hash, record_hash, action_type, timestamp,
                 execution_phase, social_phase, payload_json, integrity_level, signature,
                 source_action_ids)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "alice",
                    "forked",
                    GENESIS_HASH,
                    "fakehash",
                    "outbound_message",
                    "2026-04-15T00:00:00Z",
                    "nominal",
                    "discovery",
                    "{}",
                    3,
                    None,
                    "[]",
                ),
            )
            conn.commit()


async def test_concurrent_appends_serialize(tmp_path: Path):
    """Concurrent asyncio appends against the same agent must not fork the chain.

    Under BEGIN IMMEDIATE, the first writer acquires the SQLite write lock and
    commits; subsequent writers re-read the head (now advanced) within their
    own transaction and see prev_hash no longer matches -> HashChainBroken.
    Exactly one succeeds; the rest raise HashChainBroken. The chain stays
    intact and verify_chain returns True.
    """
    log = ActionLog(db_path=tmp_path / "run.db")
    h1 = log.append(_record("alice", GENESIS_HASH, {"i": 0}))

    N = 5

    def _build_rec(i: int) -> ActionRecord:
        # Distinct action_id per candidate so failure can't be caused by
        # action_id UNIQUE instead of the chain-head check.
        return ActionRecord(
            action_id=f"alice-concurrent-{i}",
            prev_hash=h1,
            agent_id="alice",
            action_type=ActionType.OUTBOUND_MESSAGE,
            timestamp="2026-04-15T00:00:00Z",
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=SocialPhase.DISCOVERY,
            payload={"i": i + 1},
            integrity_level=IntegrityLevel.HASH_CHAINED,
        )

    async def try_append(i: int):
        try:
            return ("ok", log.append(_build_rec(i)))
        except HashChainBroken:
            return ("broken", None)
        except Exception as e:  # pragma: no cover - defensive
            return ("err", type(e).__name__)

    outs = await asyncio.gather(*[try_append(i) for i in range(N)])
    ok_count = sum(1 for r in outs if r[0] == "ok")
    broken_count = sum(1 for r in outs if r[0] == "broken")
    assert ok_count == 1, f"expected 1 success, got {outs}"
    assert broken_count == N - 1, f"expected {N - 1} HashChainBroken, got {outs}"
    # Chain is intact after concurrent contention.
    assert log.verify_chain("alice") is True
