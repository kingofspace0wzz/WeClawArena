"""Cassette recorder for gateway sessions.

Every append to ``Session.action_log`` is mirrored to a ``cassette.jsonl``
file under the session's ``work_dir``. Each line is one JSON object
carrying the full set of :class:`ActionRecord` envelope fields needed to
reconstruct the action during replay:

``{timestamp, kind, action_id, agent_id, prev_hash, source_action_ids,
execution_phase, social_phase, integrity_level, payload}``

The enriched schema lets :class:`~clawsocialarena.gateway.replay.ReplayDriver`
rebuild the action stream without a separate ``agent_resolver`` callback
and with the original action_ids preserved, which keeps attribution
and hash-chain verification reproducible across live/replay boundaries.

The cassette is separate from the primary action log: it is a plain-text
by-design record suitable for human inspection and for the Phase E/F/H
analysis pipeline that replays full scenario traces.

The recorder holds an open append-mode file handle for the lifetime of
the session and flushes after every write so tests can read the file
mid-session. ``close()`` is idempotent and is driven by ``Session.close``.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from clawsocialarena.types import ActionRecord


class CassetteRecorder:
    """Append-only JSONL recorder for every action a Session logs.

    One instance is created per session under PASSIVE or ENFORCE when a
    ``work_dir`` is supplied. Each call to :meth:`record` writes a single
    JSON line and flushes, so partial traces survive a crash.

    The recorder is a best-effort mirror of the action log. The primary
    :class:`~clawsocialarena.action_log.ActionLog` remains the source of
    truth: if a cassette write fails (disk full, closed handle, permission
    error, etc.), callers should catch the exception and continue. The
    action log append has already succeeded by the time ``record()`` runs.
    Writes are serialized by an internal ``threading.Lock`` so concurrent
    gateway requests can append safely; the lock also covers the
    subsequent ``flush``.
    """

    def __init__(self, path: Path | str) -> None:
        """Open ``path`` in append mode, creating parents if needed."""

        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fp: TextIO | None = self._path.open("a", encoding="utf-8")
        self._lock = threading.Lock()

    def record(self, record: ActionRecord) -> None:
        """Write one enriched cassette line for ``record``.

        The line carries every :class:`ActionRecord` envelope field plus a
        wall-clock ``timestamp`` captured at write time (distinct from
        ``record.timestamp`` so replay remains insensitive to write-time
        clock drift while retaining the record-level timestamp needed for
        hash-chain reproducibility). ``kind`` is the string value of
        :attr:`ActionRecord.action_type`, kept as a separate top-level
        field so the gateway's streaming consumers do not need to parse
        ``action_type`` out of the payload.

        The payload is serialized verbatim via ``json.dumps`` with sorted
        keys so line ordering is stable across runs. Non-ASCII characters
        are preserved literally (``ensure_ascii=False``) so user-supplied
        Unicode survives round-tripping.
        """

        if self._fp is None:
            raise ValueError("cassette closed")

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "kind": record.action_type.value,
            "action_id": record.action_id,
            "agent_id": record.agent_id,
            "prev_hash": record.prev_hash,
            "source_action_ids": list(record.source_action_ids),
            "execution_phase": record.execution_phase.value,
            "social_phase": record.social_phase.value,
            "integrity_level": int(record.integrity_level),
            "payload": record.payload,
        }
        if record.signature is not None:
            entry["signature"] = record.signature
        line = json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n"
        with self._lock:
            fp = self._fp
            if fp is None:
                raise ValueError("cassette closed")
            fp.write(line)
            fp.flush()

    def close(self) -> None:
        """Close the underlying file handle; safe to call multiple times."""

        with self._lock:
            fp = self._fp
            if fp is None:
                return
            try:
                fp.close()
            finally:
                self._fp = None

    def __enter__(self) -> "CassetteRecorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
