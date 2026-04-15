from clawsocialarena.audit.attribution import AttributionGraphBuilder
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


def _pol(action_id: str, agent: str, verdict: str = "rewrite") -> ActionRecord:
    return ActionRecord(
        action_id=action_id,
        prev_hash="0" * 64,
        agent_id=agent,
        action_type=ActionType.POLICY_DECISION,
        timestamp="2026-04-15T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={"verdict": verdict, "policy_id": "p1", "reason": "x"},
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def _msg(action_id: str, agent: str) -> ActionRecord:
    return ActionRecord(
        action_id=action_id,
        prev_hash="0" * 64,
        agent_id=agent,
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-15T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={"recipient_id": "b", "content": "msg"},
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def test_empty_log_produces_empty_dag():
    builder = AttributionGraphBuilder()
    dag = builder.build(action_log=[])
    assert dag == {"nodes": [], "edges": []}


def test_no_policy_decisions_produces_empty_dag():
    builder = AttributionGraphBuilder()
    log = [_msg(f"m{i}", "a") for i in range(3)]
    dag = builder.build(action_log=log)
    assert dag == {"nodes": [], "edges": []}


def test_allow_verdict_does_not_create_node():
    builder = AttributionGraphBuilder()
    log = [_pol("p1", "a", verdict="allow")]
    dag = builder.build(action_log=log)
    assert dag == {"nodes": [], "edges": []}


def test_rewrite_verdict_creates_l0_node():
    builder = AttributionGraphBuilder()
    log = [_pol("p1", "a", verdict="rewrite")]
    dag = builder.build(action_log=log)
    assert dag["nodes"] == [{"id": "p1", "label": "L0", "agent_id": "a"}]
    assert dag["edges"] == []


def test_block_verdict_creates_l0_node():
    builder = AttributionGraphBuilder()
    log = [_pol("p1", "a", verdict="block")]
    dag = builder.build(action_log=log)
    assert dag["nodes"] == [{"id": "p1", "label": "L0", "agent_id": "a"}]


def test_message_following_violation_gets_l1_edge():
    builder = AttributionGraphBuilder(cascade_window=3)
    log = [
        _pol("p1", "a", verdict="rewrite"),
        _msg("m1", "a"),
        _msg("m2", "a"),
    ]
    dag = builder.build(action_log=log)
    # 1 L0 node (p1) + 2 L1 nodes (m1, m2)
    assert {n["id"] for n in dag["nodes"]} == {"p1", "m1", "m2"}
    # Edges link p1 to each subsequent outbound within the window
    edge_pairs = {(e["src"], e["dst"], e["label"]) for e in dag["edges"]}
    assert ("p1", "m1", "L1") in edge_pairs
    assert ("p1", "m2", "L1") in edge_pairs


def test_cascade_window_limits_edges():
    builder = AttributionGraphBuilder(cascade_window=1)
    log = [
        _pol("p1", "a", verdict="rewrite"),
        _msg("m1", "a"),  # within window
        _msg("m2", "a"),  # outside window
    ]
    dag = builder.build(action_log=log)
    edge_pairs = {(e["src"], e["dst"], e["label"]) for e in dag["edges"]}
    assert ("p1", "m1", "L1") in edge_pairs
    assert ("p1", "m2", "L1") not in edge_pairs
