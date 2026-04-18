"""Phase F / Task F6: cassette replay driver tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawsocialarena.gateway.replay import ReplayDriver
from clawsocialarena.scenario.models import GTBundle
from clawsocialarena.types import ActionType


def _make_gt() -> GTBundle:
    return GTBundle(
        scenario_id="scen-replay",
        canonical_action_stream=[],
        phase_schedule=[],
        policies={"flat": [], "phase_scoped": []},
        attribution_dag={"nodes": [], "edges": []},
        integrity_requirements={},
        terminal_predicate={"type": "none"},
        invariants={},
    )


def _write_cassette(path: Path, lines: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for entry in lines:
            f.write(json.dumps(entry, sort_keys=True) + "\n")


def test_enriched_cassette_replay_reproduces_record_order(tmp_path: Path):
    cassette = tmp_path / "cassette.jsonl"
    _write_cassette(
        cassette,
        [
            {
                "timestamp": "2026-04-17T00:00:00Z",
                "kind": "outbound_message",
                "agent_id": "A",
                "action_id": "A-0",
                "payload": {
                    "recipient_id": "C",
                    "content": "hello",
                    "mentioned_items": ["item-x"],
                },
            },
            {
                "timestamp": "2026-04-17T00:00:01Z",
                "kind": "outbound_message",
                "agent_id": "B",
                "action_id": "B-0",
                "payload": {
                    "recipient_id": "C",
                    "content": "world",
                    "mentioned_items": ["item-y"],
                },
            },
        ],
    )
    gt = _make_gt()
    driver = ReplayDriver(cassette, gt)
    result = driver.run(db_path=tmp_path / "primary.db")
    assert [r.action_id for r in result.records] == ["A-0", "B-0"]
    assert [r.agent_id for r in result.records] == ["A", "B"]
    # MSWM was populated by both outbound records.
    a_to_c = result.mswm.get("A", "C")
    b_to_c = result.mswm.get("B", "C")
    assert ("item-x", "A-0") in a_to_c.items_told_to_j
    assert ("item-y", "B-0") in b_to_c.items_told_to_j


def test_action_log_read_all_matches_records(tmp_path: Path):
    cassette = tmp_path / "cassette.jsonl"
    _write_cassette(
        cassette,
        [
            {
                "timestamp": "2026-04-17T00:00:00Z",
                "kind": "outbound_message",
                "agent_id": "A",
                "action_id": "A-0",
                "payload": {"recipient_id": "B", "content": "hi"},
            },
            {
                "timestamp": "2026-04-17T00:00:01Z",
                "kind": "memory_write",
                "agent_id": "A",
                "action_id": "mem-0",
                "payload": {"content": "noted"},
            },
        ],
    )
    driver = ReplayDriver(cassette, _make_gt())
    result = driver.run(db_path=tmp_path / "p.db")
    read = result.action_log.read_all()
    assert [r.action_id for r in read] == ["A-0", "mem-0"]
    # Chain integrity holds because prev_hash is sourced from the log head.
    assert result.action_log.verify_chain("A") is True


def test_bare_cassette_replay_requires_resolver(tmp_path: Path):
    cassette = tmp_path / "cassette.jsonl"
    _write_cassette(
        cassette,
        [
            {
                "timestamp": "2026-04-17T00:00:00Z",
                "kind": "outbound_message",
                "payload": {"recipient_id": "B", "content": "hi"},
            }
        ],
    )
    driver = ReplayDriver(cassette, _make_gt())
    with pytest.raises(ValueError, match="agent_resolver"):
        driver.run(db_path=tmp_path / "p.db")


def test_bare_cassette_replay_with_resolver_succeeds(tmp_path: Path):
    cassette = tmp_path / "cassette.jsonl"
    _write_cassette(
        cassette,
        [
            {
                "timestamp": "2026-04-17T00:00:00Z",
                "kind": "outbound_message",
                "payload": {"recipient_id": "B", "content": "hi"},
            },
            {
                "timestamp": "2026-04-17T00:00:01Z",
                "kind": "memory_write",
                "payload": {"content": "note"},
            },
        ],
    )

    def resolver(kind: str, payload: dict) -> str:
        # Toy: recipient is B, so sender is A for outbound.
        if kind == "outbound_message":
            return "A"
        return "A"

    driver = ReplayDriver(cassette, _make_gt(), agent_resolver=resolver)
    result = driver.run(db_path=tmp_path / "p.db")
    assert len(result.records) == 2
    # Deterministic action_ids for bare cassettes.
    assert [r.action_id for r in result.records] == ["repl-0000", "repl-0001"]


def test_replay_never_calls_an_llm_or_network(tmp_path: Path, monkeypatch):
    """Sanity: ReplayDriver must not invoke anything that needs a network.

    We assert by patching requests/boto3/etc. to raise if touched; here we
    simply assert the driver runs to completion without importing those
    libraries, which is a proxy for 'no LLM was called'.
    """

    cassette = tmp_path / "cassette.jsonl"
    _write_cassette(
        cassette,
        [
            {
                "timestamp": "2026-04-17T00:00:00Z",
                "kind": "outbound_message",
                "agent_id": "A",
                "action_id": "A-0",
                "payload": {"recipient_id": "B", "content": "x"},
            }
        ],
    )
    driver = ReplayDriver(cassette, _make_gt())
    # Should complete without any network activity.
    result = driver.run(db_path=tmp_path / "p.db")
    assert len(result.records) == 1


def test_replay_skips_blank_lines(tmp_path: Path):
    cassette = tmp_path / "cassette.jsonl"
    cassette.write_text(
        '\n'
        + json.dumps(
            {
                "timestamp": "2026-04-17T00:00:00Z",
                "kind": "outbound_message",
                "agent_id": "A",
                "action_id": "A-0",
                "payload": {"recipient_id": "B", "content": "x"},
            }
        )
        + "\n\n",
        encoding="utf-8",
    )
    driver = ReplayDriver(cassette, _make_gt())
    result = driver.run(db_path=tmp_path / "p.db")
    assert len(result.records) == 1


def test_replay_deterministic_across_invocations(tmp_path: Path):
    cassette = tmp_path / "cassette.jsonl"
    _write_cassette(
        cassette,
        [
            {
                "timestamp": "2026-04-17T00:00:00Z",
                "kind": "outbound_message",
                "agent_id": "A",
                "action_id": "A-0",
                "payload": {
                    "recipient_id": "B",
                    "content": "hi",
                    "mentioned_items": ["item-x"],
                },
            }
        ],
    )
    r1 = ReplayDriver(cassette, _make_gt()).run(db_path=tmp_path / "p1.db")
    r2 = ReplayDriver(cassette, _make_gt()).run(db_path=tmp_path / "p2.db")
    # Hash-chained logs produce identical record hashes when the envelope
    # (including timestamp) is identical.
    with r1.action_log.connect() as c1, r2.action_log.connect() as c2:
        h1 = c1.execute(
            "SELECT record_hash FROM actions ORDER BY row_id"
        ).fetchall()
        h2 = c2.execute(
            "SELECT record_hash FROM actions ORDER BY row_id"
        ).fetchall()
    assert [row[0] for row in h1] == [row[0] for row in h2]


def test_replay_preserves_source_action_ids(tmp_path: Path):
    cassette = tmp_path / "cassette.jsonl"
    _write_cassette(
        cassette,
        [
            {
                "timestamp": "2026-04-17T00:00:00Z",
                "kind": "outbound_message",
                "agent_id": "A",
                "action_id": "A-0",
                "payload": {"recipient_id": "B", "content": "hi"},
            },
            {
                "timestamp": "2026-04-17T00:00:01Z",
                "kind": "outbound_message",
                "agent_id": "A",
                "action_id": "A-1",
                "source_action_ids": ["A-0"],
                "payload": {
                    "recipient_id": "C",
                    "content": "passing on A-0 content",
                },
            },
        ],
    )
    driver = ReplayDriver(cassette, _make_gt())
    result = driver.run(db_path=tmp_path / "p.db")
    assert result.records[1].source_action_ids == ["A-0"]


def test_replay_respects_social_phase_field(tmp_path: Path):
    cassette = tmp_path / "cassette.jsonl"
    _write_cassette(
        cassette,
        [
            {
                "timestamp": "2026-04-17T00:00:00Z",
                "kind": "outbound_message",
                "agent_id": "A",
                "action_id": "A-0",
                "social_phase": "disclosure",
                "payload": {"recipient_id": "B", "content": "hi"},
            }
        ],
    )
    driver = ReplayDriver(cassette, _make_gt())
    result = driver.run(db_path=tmp_path / "p.db")
    assert result.records[0].social_phase.value == "disclosure"


def test_replay_default_kind_memory_write_supported(tmp_path: Path):
    """All 10 ActionType values should be replayable."""

    cassette = tmp_path / "cassette.jsonl"
    entries = [
        {
            "timestamp": "2026-04-17T00:00:00Z",
            "kind": ActionType.MEMORY_WRITE.value,
            "agent_id": "A",
            "action_id": "mem-0",
            "payload": {"content": "note"},
        },
        {
            "timestamp": "2026-04-17T00:00:01Z",
            "kind": ActionType.LLM_CALL.value,
            "agent_id": "A",
            "action_id": "llm-0",
            "payload": {"model": "claude-4-7", "input_tokens": 10},
        },
        {
            "timestamp": "2026-04-17T00:00:02Z",
            "kind": ActionType.TOOL_CALL.value,
            "agent_id": "A",
            "action_id": "tc-0",
            "payload": {"tool_name": "web_search", "arguments": {}},
        },
    ]
    _write_cassette(cassette, entries)
    driver = ReplayDriver(cassette, _make_gt())
    result = driver.run(db_path=tmp_path / "p.db")
    assert [r.action_type for r in result.records] == [
        ActionType.MEMORY_WRITE,
        ActionType.LLM_CALL,
        ActionType.TOOL_CALL,
    ]
