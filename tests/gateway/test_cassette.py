"""Tests for the gateway CassetteRecorder (Task A5).

Every append to ``Session.action_log`` should also emit a single JSON line
to ``cassette.jsonl`` under the session's ``work_dir``. The recorder
captures ``{timestamp, kind, payload}`` with the kind matching the string
value of the corresponding ``ActionType``. Baseline sessions and sessions
built without a ``work_dir`` must leave ``Session.cassette`` as ``None``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from clawsocialarena.gateway.cassette import CassetteRecorder
from clawsocialarena.gateway.session import Session
from clawsocialarena.types import AuditCondition


def _drive_five_record_calls(session: Session) -> None:
    """Invoke each of the five record_* helpers once in a fixed order.

    The order matches the ordering we assert in the cassette test so that
    kind sequence is deterministic: outbound, tool_call, tool_observation,
    memory_write, llm_call.
    """

    session.record_outbound(
        sender_id="alice",
        recipient_id="bob",
        content="hello bob",
    )
    tc_id = session.record_tool_call(
        agent_id="alice",
        tool_name="web_search",
        arguments={"q": "hi"},
    )
    session.record_tool_observation(
        agent_id="alice",
        tool_call_action_id=tc_id or "tc-stub",
        tool_name="web_search",
        observation="1 result",
    )
    session.record_memory_write(
        agent_id="alice",
        content="bob prefers async",
    )
    session.record_llm_call(
        agent_id="alice",
        input_tokens=10,
        output_tokens=5,
        latency_ms=100,
        model="claude-4-7-opus",
    )


def test_cassette_captures_every_action(tmp_path: Path) -> None:
    session = Session.build(
        scenario_id="a5-passive",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "a5.db",
        work_dir=tmp_path,
    )

    assert isinstance(session.cassette, CassetteRecorder)

    _drive_five_record_calls(session)
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
        assert set(entry.keys()) == {"timestamp", "kind", "payload"}
        assert entry["kind"] == expected_kind
        assert isinstance(entry["payload"], dict)
        assert isinstance(entry["timestamp"], str)


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


def test_cassette_close_is_idempotent(tmp_path: Path) -> None:
    recorder = CassetteRecorder(tmp_path / "cassette.jsonl")
    recorder.record(kind="outbound_message", payload={"x": 1})
    recorder.close()
    recorder.close()  # second call must not raise


def test_cassette_timestamp_is_iso_utc(tmp_path: Path) -> None:
    session = Session.build(
        scenario_id="a5-timestamp",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "ts.db",
        work_dir=tmp_path,
    )

    session.record_memory_write(agent_id="alice", content="note")
    session.close()

    cassette_path = tmp_path / "cassette.jsonl"
    lines = cassette_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    entry = json.loads(lines[0])
    parsed = datetime.fromisoformat(entry["timestamp"])
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(parsed)
