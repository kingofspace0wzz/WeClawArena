"""Tests for the gateway CassetteRecorder.

Every append to ``Session.action_log`` should also emit a single JSON line
to ``cassette.jsonl`` under the session's ``work_dir``. As of the Phase G
enrichment, each line carries the full :class:`ActionRecord` envelope so
that :class:`~clawsocialarena.gateway.replay.ReplayDriver` can rehydrate
the action without an external ``agent_resolver``.

The enriched schema is:

``{timestamp, kind, action_id, agent_id, prev_hash, source_action_ids,
execution_phase, social_phase, integrity_level, payload}``

Baseline sessions and sessions built without a ``work_dir`` must leave
``Session.cassette`` as ``None``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from clawsocialarena.gateway.cassette import CassetteRecorder
from clawsocialarena.gateway.session import Session
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    AuditCondition,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


ENRICHED_KEYS = {
    "timestamp",
    "kind",
    "action_id",
    "agent_id",
    "prev_hash",
    "source_action_ids",
    "execution_phase",
    "social_phase",
    "integrity_level",
    "payload",
}


async def _drive_five_record_calls(session: Session) -> None:
    """Invoke each of the five record_* helpers once in a fixed order.

    The order matches the ordering we assert in the cassette test so that
    kind sequence is deterministic: outbound, tool_call, tool_observation,
    memory_write, llm_call. Every ``record_*`` helper is async because
    the session dispatches policy hooks inline.
    """

    await session.record_outbound(
        sender_id="alice",
        recipient_id="bob",
        content="hello bob",
    )
    tc_outcome = await session.record_tool_call(
        agent_id="alice",
        tool_name="web_search",
        arguments={"q": "hi"},
    )
    await session.record_tool_observation(
        agent_id="alice",
        tool_call_action_id=tc_outcome.action_id or "tc-stub",
        tool_name="web_search",
        observation="1 result",
    )
    await session.record_memory_write(
        agent_id="alice",
        content="bob prefers async",
    )
    await session.record_llm_call(
        agent_id="alice",
        input_tokens=10,
        output_tokens=5,
        latency_ms=100,
        model="claude-4-7-opus",
    )


async def test_cassette_captures_every_action(tmp_path: Path) -> None:
    session = Session.build(
        scenario_id="a5-passive",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "a5.db",
        work_dir=tmp_path,
    )

    assert isinstance(session.cassette, CassetteRecorder)

    await _drive_five_record_calls(session)
    session.close()

    cassette_path = tmp_path / "cassette.jsonl"
    assert cassette_path.exists()

    lines = cassette_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5

    expected_kinds = [
        "outbound_message",
        "tool_call",
        "tool_observation_return",
        "memory_write",
        "llm_call",
    ]
    for line, expected_kind in zip(lines, expected_kinds):
        entry = json.loads(line)
        # Enriched keys are always present; ``signature`` is optional.
        assert ENRICHED_KEYS.issubset(entry.keys())
        assert entry["kind"] == expected_kind
        assert entry["agent_id"] == "alice"
        assert isinstance(entry["payload"], dict)
        assert isinstance(entry["timestamp"], str)
        # action_id is a non-empty string minted by the session.
        assert isinstance(entry["action_id"], str) and entry["action_id"]
        # social/execution phase round-trip as their string values.
        assert entry["social_phase"] in {p.value for p in SocialPhase}
        assert entry["execution_phase"] in {p.value for p in ExecutionPhase}
        assert isinstance(entry["integrity_level"], int)


def test_cassette_is_none_for_baseline_or_missing_work_dir(tmp_path: Path) -> None:
    baseline_session = Session.build(
        scenario_id="a5-baseline",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",
        work_dir=tmp_path,
    )
    assert baseline_session.cassette is None

    passive_without_work_dir = Session.build(
        scenario_id="a5-no-work-dir",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "nowd.db",
    )
    assert passive_without_work_dir.cassette is None
    passive_without_work_dir.close()


def _make_record(**overrides) -> ActionRecord:
    """Build a minimal ActionRecord suitable for cassette tests."""

    base = dict(
        action_id="act-000000000001",
        prev_hash="0" * 64,
        agent_id="alice",
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-17T00:00:00+00:00",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={"recipient_id": "bob", "content": "x"},
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )
    base.update(overrides)
    return ActionRecord(**base)


def test_cassette_close_is_idempotent(tmp_path: Path) -> None:
    recorder = CassetteRecorder(tmp_path / "cassette.jsonl")
    recorder.record(_make_record())
    recorder.close()
    recorder.close()  # second call must not raise


def test_cassette_roundtrip_non_ascii(tmp_path: Path) -> None:
    """Non-ASCII content should survive as literal UTF-8, not ``\\uXXXX`` escapes.

    The recorder uses ``ensure_ascii=False`` so Chinese characters, emoji,
    and accented Latin letters appear verbatim in ``cassette.jsonl``. This
    keeps the file human-readable for the Phase H analysis pipeline and
    for cross-tool inspection.
    """

    cassette_path = tmp_path / "cassette.jsonl"
    recorder = CassetteRecorder(cassette_path)
    content = "hello 你好 \U0001f44b caf\u00e9"
    recorder.record(
        _make_record(payload={"recipient_id": "bob", "content": content})
    )
    recorder.close()

    raw_bytes = cassette_path.read_bytes()
    assert "你好".encode("utf-8") in raw_bytes
    assert "\U0001f44b".encode("utf-8") in raw_bytes
    assert "caf\u00e9".encode("utf-8") in raw_bytes
    assert b"\\u" not in raw_bytes

    entry = json.loads(cassette_path.read_text(encoding="utf-8").splitlines()[0])
    assert entry["payload"]["content"] == content


async def test_cassette_timestamp_is_iso_utc(tmp_path: Path) -> None:
    session = Session.build(
        scenario_id="a5-timestamp",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "ts.db",
        work_dir=tmp_path,
    )

    await session.record_memory_write(agent_id="alice", content="note")
    session.close()

    cassette_path = tmp_path / "cassette.jsonl"
    lines = cassette_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    entry = json.loads(lines[0])
    parsed = datetime.fromisoformat(entry["timestamp"])
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(parsed)


async def test_cassette_preserves_action_ids_for_replay(tmp_path: Path) -> None:
    """Enriched cassettes must carry the exact action_id the session minted.

    Phase G wires :class:`~clawsocialarena.gateway.replay.ReplayDriver` to
    read action_ids out of the cassette so the replayed records line up
    with the original attribution DAG and hash-chain verification.
    """

    session = Session.build(
        scenario_id="a5-ids",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "ids.db",
        work_dir=tmp_path,
    )
    outcome = await session.record_outbound(
        sender_id="alice", recipient_id="bob", content="hi"
    )
    session.close()

    entry = json.loads(
        (tmp_path / "cassette.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert outcome.action_id is not None
    assert entry["action_id"] == outcome.action_id
    # prev_hash was captured at record time; it should be a 64-char hex digest
    # (or the genesis all-zero string).
    assert isinstance(entry["prev_hash"], str) and len(entry["prev_hash"]) == 64
