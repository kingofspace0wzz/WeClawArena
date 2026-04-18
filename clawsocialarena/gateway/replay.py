"""Cassette replay driver for offline evaluation.

The :class:`CassetteRecorder` persists every action as a JSONL line of
``{timestamp, kind, payload}``. For replay we need a bit more than the
bare v1 format carries — specifically the sending ``agent_id``, a stable
``action_id``, and any ``source_action_ids`` that the original live run
would have stamped on the record. Two input formats are supported:

1. **Enriched cassette** — each line is
   ``{timestamp, kind, payload, agent_id, action_id[, source_action_ids]}``.
   This is the format v2 cassettes should carry going forward; the
   gateway will start recording it when Phase H wires the final batch
   runner. For Phase F the fixture-level tests hand-craft it directly.
2. **Bare cassette** — legacy ``{timestamp, kind, payload}`` lines. The
   caller supplies an ``agent_resolver`` callable that returns the
   agent_id for a given ``(kind, payload)`` pair. ``action_id`` is
   generated as ``repl-{index:04d}`` for deterministic ordering.

The driver is pure: it never touches the network, an LLM, or a live
gateway. Output is an in-memory :class:`~clawsocialarena.action_log.ActionLog`
persisted under a caller-supplied directory plus an
:class:`~clawsocialarena.audit.mswm.MSWM` rebuilt from the stream.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.mswm import MSWM
from clawsocialarena.scenario.models import GTBundle
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


AgentResolver = Callable[[str, dict], str]


@dataclass
class ReplayResult:
    """Output of :meth:`ReplayDriver.run`.

    Attributes:
        action_log: The rebuilt primary :class:`ActionLog` (on-disk SQLite).
        mswm: The replayed :class:`MSWM` after applying every action in order.
        records: Ordered list of :class:`ActionRecord` instances that were
            appended. Mirrors the log's ``read_all()`` output and is
            provided for convenience so callers can assert on ordering
            without re-reading the DB.
    """

    action_log: ActionLog
    mswm: MSWM
    records: list[ActionRecord]


class ReplayDriver:
    """Deterministic cassette replay without any LLM or gateway involvement.

    Usage:

        driver = ReplayDriver(cassette_path, gt_bundle)
        result = driver.run(db_path=workdir / "primary.db")

    ``gt_bundle`` currently scopes the ``scenario_id`` and (future) the
    phase schedule so the replayed records can carry the right phase.
    The scenario validator's GT is the canonical source of truth; here
    we only read what we need to stamp phases and (in future) verify
    the replay matches the planted action stream.

    The driver is not re-entrant; create one instance per replay.
    """

    def __init__(
        self,
        cassette_path: Path | str,
        gt_bundle: GTBundle,
        *,
        agent_resolver: AgentResolver | None = None,
    ) -> None:
        self._cassette_path = Path(cassette_path)
        self._gt = gt_bundle
        self._agent_resolver = agent_resolver

    def run(self, *, db_path: Path | str) -> ReplayResult:
        """Replay the cassette into a fresh ActionLog + MSWM.

        ``db_path`` is the on-disk location for the primary log SQLite
        file; callers typically put it alongside the cassette under a
        run work directory. Parent directories are created if absent.

        The method reads the cassette line by line, decodes the JSON,
        resolves the ``agent_id`` (via the enriched field or the
        ``agent_resolver`` callback), stamps ``action_id`` deterministically
        when absent, and appends an :class:`ActionRecord` to the log.
        MSWM is updated after each append via
        :meth:`MSWM.on_action`, exactly as the live session does.
        """

        log = ActionLog(db_path)
        mswm = MSWM()
        records: list[ActionRecord] = []

        for idx, entry in enumerate(self._iter_entries()):
            kind = entry["kind"]
            payload = entry.get("payload") or {}
            agent_id = self._resolve_agent(entry, kind, payload, idx)
            action_id = entry.get("action_id") or f"repl-{idx:04d}"
            timestamp = entry.get("timestamp") or self._synthetic_ts(idx)
            social_phase = SocialPhase(
                entry.get("social_phase") or SocialPhase.DISCOVERY.value
            )
            execution_phase = ExecutionPhase(
                entry.get("execution_phase") or ExecutionPhase.NOMINAL.value
            )
            integrity_level = IntegrityLevel(
                int(entry.get("integrity_level") or IntegrityLevel.HASH_CHAINED)
            )
            signature = entry.get("signature")
            sources = list(entry.get("source_action_ids") or [])

            record = ActionRecord(
                action_id=action_id,
                prev_hash=log.head_hash(agent_id),
                agent_id=agent_id,
                action_type=ActionType(kind),
                timestamp=timestamp,
                execution_phase=execution_phase,
                social_phase=social_phase,
                payload=dict(payload),
                integrity_level=integrity_level,
                signature=signature,
                source_action_ids=sources,
            )
            log.append(record)
            mswm.on_action(record)
            records.append(record)

        return ReplayResult(action_log=log, mswm=mswm, records=records)

    def _iter_entries(self) -> Iterable[dict]:
        """Yield each cassette line parsed into a dict.

        Blank lines are silently skipped so trailing newlines do not
        crash the replay. JSON parse errors surface verbatim — a
        corrupted cassette is an operational failure the caller should
        see, not silently ignore.
        """

        with self._cassette_path.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                yield json.loads(stripped)

    def _resolve_agent(
        self, entry: dict, kind: str, payload: dict, idx: int
    ) -> str:
        """Return the agent_id for a cassette entry.

        Enriched-format cassettes carry ``agent_id`` directly. Bare
        cassettes rely on a user-supplied resolver. When neither is
        available we raise ``ValueError`` — this is a programmer error,
        not a data error.
        """

        explicit = entry.get("agent_id")
        if isinstance(explicit, str) and explicit:
            return explicit
        if self._agent_resolver is not None:
            return self._agent_resolver(kind, payload)
        raise ValueError(
            f"cassette entry #{idx} ({kind}) has no agent_id and no "
            f"agent_resolver was supplied; replay cannot proceed"
        )

    @staticmethod
    def _synthetic_ts(idx: int) -> str:
        """Deterministic ISO timestamp for legacy bare cassettes.

        We don't want the replay record's timestamp to depend on
        wall-clock — that would break hash-chain reproducibility. When
        the cassette omits a timestamp we synthesize one at a fixed
        reference epoch offset by the line index.
        """

        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        seconds = base.timestamp() + idx
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
