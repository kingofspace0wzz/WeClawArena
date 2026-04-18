"""Phase F / Task F5: v2 EvalRunner end-to-end smoke test.

Builds a tiny hand-crafted scenario:
- primary ActionLog with 3 outbound messages (hash-chained correctly)
- matching shadow log (should yield recoverability = 1.0)
- GT bundle with no policies declared
- cassette file with a known hash

Drives EvalRunner.evaluate and asserts:
- Stage 1 sets gateway_invariant_passed to True (chains verify).
- Stage 2 populates phase_tag_counts from action records.
- Stage 3 fills SAF dims with 1.0 (empty GT policies + perfect log).
- Stage 5 surfaces attribution counts in diagnostics.
- v2 scorecard fields (cassette_hash, live_or_replay, episode_graph_id)
  round-trip through the return value.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.shadow_log import ShadowLog
from clawsocialarena.eval.runner import EvalRunner
from clawsocialarena.hashing import GENESIS_HASH, hash_action
from clawsocialarena.scenario.models import GTBundle
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


def _canonical_envelope(rec: ActionRecord) -> dict:
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
        "source_action_ids": list(rec.source_action_ids),
    }


def _append_chained(log: ActionLog, agent: str, idx: int, phase: SocialPhase) -> str:
    """Append a properly hash-chained outbound record to ``log``."""

    prev = log.head_hash(agent)
    rec = ActionRecord(
        action_id=f"{agent}-{idx}",
        prev_hash=prev,
        agent_id=agent,
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-17T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=phase,
        payload={
            "recipient_id": "C",
            "content": f"msg-{idx}",
            "mentioned_items": [f"item-{idx}"],
        },
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )
    return log.append(rec)


def _build_run(tmp_path: Path) -> tuple[ActionLog, ShadowLog, GTBundle, Path]:
    primary = ActionLog(tmp_path / "primary.db")
    shadow = ShadowLog(tmp_path / "shadow.db")

    phases = [
        SocialPhase.DISCOVERY,
        SocialPhase.DISCLOSURE,
        SocialPhase.REPAIR,
    ]
    for i, ph in enumerate(phases):
        _append_chained(primary, "A", i, ph)
        _append_chained(shadow, "A", i, ph)

    gt = GTBundle(
        scenario_id="scen-F5",
        canonical_action_stream=[],
        phase_schedule=[],
        policies={"flat": [], "phase_scoped": []},
        attribution_dag={"nodes": [], "edges": []},
        integrity_requirements={},
        terminal_predicate={"type": "none"},
        invariants={},
    )

    cassette_path = tmp_path / "cassette.jsonl"
    cassette_path.write_text('{"line":"1"}\n', encoding="utf-8")

    return primary, shadow, gt, cassette_path


def test_eval_runner_v2_emits_v2_scorecard(tmp_path: Path):
    primary, shadow, gt, cassette = _build_run(tmp_path)
    runner = EvalRunner()
    sc = runner.evaluate(
        action_log=primary,
        shadow_log=shadow,
        gt=gt,
        cassette_path=cassette,
        live_or_replay="live",
        episode_graph_id=None,
        meta={"model": "test-model", "condition": "passive"},
    )
    assert sc.scenario_id == "scen-F5"
    assert sc.live_or_replay == "live"
    assert sc.episode_graph_id is None
    # cassette hash is the sha256 of the file's bytes.
    expected_hash = hashlib.sha256(cassette.read_bytes()).hexdigest()
    assert sc.cassette_hash == expected_hash


def test_stage1_flags_gateway_invariant_on_perfect_chain(tmp_path: Path):
    primary, shadow, gt, cassette = _build_run(tmp_path)
    runner = EvalRunner()
    sc = runner.evaluate(
        action_log=primary, shadow_log=shadow, gt=gt, cassette_path=cassette
    )
    assert sc.gateway_invariant_passed is True
    # Per-agent verdicts land in diagnostics.
    assert sc.diagnostics["chain_integrity_primary"]["A"] is True
    assert sc.diagnostics["chain_integrity_shadow"]["A"] is True


def test_stage1_flags_broken_chain(tmp_path: Path):
    """Corrupt the primary log after append; Stage 1 must report False."""

    primary, shadow, gt, cassette = _build_run(tmp_path)
    # Rewrite the first record's payload_json directly in SQLite.
    with primary.connect() as conn:
        conn.execute(
            "UPDATE actions SET payload_json = ? WHERE action_id = ?",
            ('{"content":"TAMPERED"}', "A-0"),
        )
        conn.commit()

    runner = EvalRunner()
    sc = runner.evaluate(
        action_log=primary, shadow_log=shadow, gt=gt, cassette_path=cassette
    )
    assert sc.gateway_invariant_passed is False
    assert sc.diagnostics["chain_integrity_primary"]["A"] is False


def test_stage2_tags_phases_from_records(tmp_path: Path):
    primary, shadow, gt, _ = _build_run(tmp_path)
    runner = EvalRunner()
    sc = runner.evaluate(action_log=primary, shadow_log=shadow, gt=gt)
    tags = sc.diagnostics["phase_tag_counts"]
    assert tags["discovery"] == 1
    assert tags["disclosure"] == 1
    assert tags["repair"] == 1


def test_stage3_saf_dims_populated(tmp_path: Path):
    primary, shadow, gt, _ = _build_run(tmp_path)
    runner = EvalRunner()
    sc = runner.evaluate(action_log=primary, shadow_log=shadow, gt=gt)
    expected = {
        "recoverability",
        "policy_checkability",
        "attribution",
        "evidence_integrity",
        "phase_scoped_policy",
    }
    assert set(sc.saf.dims.keys()) == expected
    # With perfect logs + empty policies the overall score is 1.0.
    assert sc.saf.overall == 1.0
    assert all(sc.saf.passes.values())


def test_stage5_surfaces_mswm_and_dag_counts(tmp_path: Path):
    primary, shadow, gt, _ = _build_run(tmp_path)
    runner = EvalRunner()
    sc = runner.evaluate(action_log=primary, shadow_log=shadow, gt=gt)
    # MSWM was populated by the three outbound messages; attribution DAG
    # falls back to proximity since no policy_decision rows exist. The
    # counts themselves just need to be present (not specific values) —
    # the contract is that Stage 5 exposes them.
    assert "mswm_peer_pairs" in sc.diagnostics
    assert "attribution_node_count" in sc.diagnostics
    assert "attribution_edge_count" in sc.diagnostics


def test_missing_cassette_path_yields_empty_hash(tmp_path: Path):
    primary, shadow, gt, _ = _build_run(tmp_path)
    runner = EvalRunner()
    sc = runner.evaluate(action_log=primary, shadow_log=shadow, gt=gt)
    assert sc.cassette_hash == ""


def test_episode_graph_id_surfaces_in_diagnostics(tmp_path: Path):
    primary, shadow, gt, _ = _build_run(tmp_path)
    runner = EvalRunner()
    sc = runner.evaluate(
        action_log=primary,
        shadow_log=shadow,
        gt=gt,
        episode_graph_id="graph-alpha",
    )
    assert sc.episode_graph_id == "graph-alpha"
    assert sc.diagnostics["episode_graph_id"] == "graph-alpha"


def test_meta_is_carried_through_unchanged(tmp_path: Path):
    primary, shadow, gt, _ = _build_run(tmp_path)
    runner = EvalRunner()
    sc = runner.evaluate(
        action_log=primary,
        shadow_log=shadow,
        gt=gt,
        meta={"condition": "enforce", "model": "gpt-5"},
    )
    assert sc.meta["condition"] == "enforce"
    assert sc.meta["model"] == "gpt-5"


def test_replay_mode_sets_live_or_replay(tmp_path: Path):
    primary, shadow, gt, cassette = _build_run(tmp_path)
    runner = EvalRunner()
    sc = runner.evaluate(
        action_log=primary,
        shadow_log=shadow,
        gt=gt,
        cassette_path=cassette,
        live_or_replay="replay",
    )
    assert sc.live_or_replay == "replay"
    # Ensure the private helpers aren't needed here — verify the scorecard
    # hashes align with a manual recompute.
    expected = hashlib.sha256(cassette.read_bytes()).hexdigest()
    # Sanity: hash_action matches the library's own hashing (smoke).
    _ = hash_action(prev_hash=GENESIS_HASH, payload=_canonical_envelope(primary.read_all()[0]))
    assert sc.cassette_hash == expected
