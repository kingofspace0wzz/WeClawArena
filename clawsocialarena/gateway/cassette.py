"""Cassette recorder for gateway sessions (Task A5).

Every append to ``Session.action_log`` is mirrored to a ``cassette.jsonl``
file under the session's ``work_dir``. Each line is one JSON object with
``{timestamp, kind, payload}`` where ``timestamp`` is an ISO 8601 UTC
string and ``kind`` is the string value of the corresponding
``ActionType``. The cassette is separate from the primary action log: it
is a plain-text by-design record suitable for human inspection and for
the phase E/F analysis pipeline that replays full scenario traces.

The recorder holds an open append-mode file handle for the lifetime of
the session and flushes after every write so tests can read the file
mid-session. ``close()`` is idempotent and is driven by ``Session.close``.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class CassetteRecorder:
    """Append-only JSONL recorder for every action a Session logs.

    One instance is created per session under PASSIVE or ENFORCE when a
    ``work_dir`` is supplied. Each call to :meth:`record` writes a single
    JSON line and flushes, so partial traces survive a crash.

    The recorder is a best-effort mirror of the action log. The primary
    ``ActionLog`` remains the source of truth: if a cassette write fails
    (disk full, closed handle, permission error, etc.), callers should
    catch the exception and continue. The action log append has already
    succeeded by the time ``record()`` runs. Writes are serialized by an
    internal ``threading.Lock`` so concurrent gateway requests can append
    safely; the lock also covers the subsequent ``flush``.
    """

    def __init__(self, path: Path | str) -> None:
        """Open ``path`` in append mode, creating parents if needed."""

        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self._path.open("a", encoding="utf-8")
        self._lock = threading.Lock()

    def record(self, *, kind: str, payload: dict[str, Any]) -> None:
        """Write one cassette line: ``{timestamp, kind, payload}``.

        ``timestamp`` is an ISO 8601 UTC string captured at call time.
        ``kind`` should be the string value of an :class:`ActionType`.
        ``payload`` is serialized verbatim via ``json.dumps`` with sorted
        keys so the line ordering is stable across runs. Non-ASCII
        characters are preserved literally (``ensure_ascii=False``) so
        user-supplied Unicode survives round-tripping.
        """

        if self._fp is None:
            raise ValueError("cassette closed")

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "payload": payload,
        }
        line = json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n"
        with self._lock:
            if self._fp is None:
                raise ValueError("cassette closed")
            self._fp.write(line)
            self._fp.flush()

    def close(self) -> None:
        """Close the underlying file handle; safe to call multiple times."""

        with self._lock:
            if self._fp is None:
                return
            try:
                self._fp.close()
            finally:
                self._fp = None

    def __enter__(self) -> "CassetteRecorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
