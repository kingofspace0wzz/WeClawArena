import pytest
from pathlib import Path

from clawsocialarena.action_log import ActionLog, HashChainBroken
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
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
