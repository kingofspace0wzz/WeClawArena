"""SQLite-backed append-only action log with per-agent hash chains.

Design choice: the stored hash canonicalizes over the full record envelope
minus ``prev_hash`` (an input to the hash) and ``record_hash`` (the output).
Hashing only ``payload`` leaves ``social_phase``, ``integrity_level``,
``execution_phase``, ``timestamp``, ``action_type``, ``agent_id``,
``action_id``, and ``signature`` exposed to silent SQL tampering while
``verify_chain`` would still report True. SAF dimensions σ (Evidence
Integrity) and φ (Phase-Scoped Policy Auditability) score against these
fields, so the chain must bind to them.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from pathlib import Path
from typing import Iterator

from clawsocialarena.hashing import GENESIS_HASH, hash_action
from clawsocialarena.types import ActionRecord


class HashChainBroken(ValueError):
    """Raised when an appended record's prev_hash does not match the chain head."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS actions (
    row_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id     TEXT    NOT NULL,
    action_id    TEXT    NOT NULL UNIQUE,
    prev_hash    TEXT    NOT NULL,
    record_hash  TEXT    NOT NULL,
    action_type  TEXT    NOT NULL,
    timestamp    TEXT    NOT NULL,
    execution_phase TEXT NOT NULL,
    social_phase TEXT    NOT NULL,
    payload_json TEXT    NOT NULL,
    integrity_level INTEGER NOT NULL,
    signature    TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent ON actions(agent_id, row_id);
"""


def _canonical_envelope(rec: ActionRecord) -> dict:
    """Return the canonical dict of hashable fields for a record.

    Excludes ``prev_hash`` (an input to ``hash_action``) and ``record_hash``
    (the output). All other envelope fields are included so that SQL tampering
    on any of them will break ``verify_chain``.
    """

    return {
        "action_id": rec.action_id,
        "agent_id": rec.agent_id,
        "action_type": rec.action_type.value,
        "timestamp": rec.timestamp,
        "execution_phase": rec.execution_phase.value,
        "social_phase": rec.social_phase.value,
        "payload": rec.payload,
        "integrity_level": int(rec.integrity_level),
        "signature": rec.signature,
    }


class ActionLog:
    """Append-only, hash-chained action log persisted to SQLite."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(_SCHEMA)

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def head_hash(self, agent_id: str) -> str:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT record_hash FROM actions WHERE agent_id = ? ORDER BY row_id DESC LIMIT 1",
                (agent_id,),
            ).fetchone()
        return row["record_hash"] if row else GENESIS_HASH

    def append(self, rec: ActionRecord) -> str:
        head = self.head_hash(rec.agent_id)
        if rec.prev_hash != head:
            raise HashChainBroken(
                f"prev_hash {rec.prev_hash[:8]}... does not match head {head[:8]}... for {rec.agent_id}"
            )
        payload_json = json.dumps(rec.payload, sort_keys=True, separators=(",", ":"))
        record_hash = hash_action(prev_hash=rec.prev_hash, payload=_canonical_envelope(rec))
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO actions
                (agent_id, action_id, prev_hash, record_hash, action_type, timestamp,
                 execution_phase, social_phase, payload_json, integrity_level, signature)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rec.agent_id,
                    rec.action_id,
                    rec.prev_hash,
                    record_hash,
                    rec.action_type.value,
                    rec.timestamp,
                    rec.execution_phase.value,
                    rec.social_phase.value,
                    payload_json,
                    int(rec.integrity_level),
                    rec.signature,
                ),
            )
            conn.commit()
        return record_hash

    def read_all(self) -> list[ActionRecord]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM actions ORDER BY row_id ASC").fetchall()
        return [self._row_to_record(r) for r in rows]

    def verify_chain(self, agent_id: str) -> bool:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM actions WHERE agent_id = ? ORDER BY row_id ASC",
                (agent_id,),
            ).fetchall()
        prev = GENESIS_HASH
        for r in rows:
            envelope = {
                "action_id": r["action_id"],
                "agent_id": r["agent_id"],
                "action_type": r["action_type"],
                "timestamp": r["timestamp"],
                "execution_phase": r["execution_phase"],
                "social_phase": r["social_phase"],
                "payload": json.loads(r["payload_json"]),
                "integrity_level": int(r["integrity_level"]),
                "signature": r["signature"],
            }
            expected = hash_action(prev_hash=prev, payload=envelope)
            if expected != r["record_hash"]:
                return False
            if r["prev_hash"] != prev:
                return False
            prev = r["record_hash"]
        return True

    def _row_to_record(self, r: sqlite3.Row) -> ActionRecord:
        return ActionRecord.model_validate(
            {
                "action_id": r["action_id"],
                "prev_hash": r["prev_hash"],
                "agent_id": r["agent_id"],
                "action_type": r["action_type"],
                "timestamp": r["timestamp"],
                "execution_phase": r["execution_phase"],
                "social_phase": r["social_phase"],
                "payload": json.loads(r["payload_json"]),
                "integrity_level": r["integrity_level"],
                "signature": r["signature"],
            }
        )
