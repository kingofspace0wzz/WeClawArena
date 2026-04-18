from clawsocialarena.audit.attribution import AttributionGraphBuilder
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


def _pol(
    action_id: str,
    agent: str,
    verdict: str = "rewrite",
    *,
    target_action_id: str | None = None,
) -> ActionRecord:
    payload: dict = {"verdict": verdict, "policy_id": "p1", "reason": "x"}
    if target_action_id is not None:
        payload["target_action_id"] = target_action_id
    return ActionRecord(
        action_id=action_id,
        prev_hash="0" * 64,
        agent_id=agent,
        action_type=ActionType.POLICY_DECISION,
        timestamp="2026-04-15T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload=payload,
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


def _record_with_sources(agent: str, idx: int, source_ids: list[str]) -> ActionRecord:
    return ActionRecord(
        action_id=f"{agent}-{idx}",
        prev_hash="0" * 64,
        agent_id=agent,
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-15T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={"recipient_id": "b", "content": "msg"},
        integrity_level=IntegrityLevel.HASH_CHAINED,
        source_action_ids=source_ids,
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


def test_causal_attribution_roots_at_target_action() -> None:
    """Fix-2 rooting: the target action is L0; its source_action_ids are L1.

    Previously these tests fabricated descendants that cited the
    policy_decision as a source — a pattern that does not occur in real
    gateway traces, because agents do not observe their own
    policy_decision rows. The replacement is a realistic shape: an
    outbound action cites an upstream outbound via source_action_ids,
    and a policy_decision names the downstream outbound as its target.
    """

    builder = AttributionGraphBuilder(cascade_window=0)
    upstream = _record_with_sources("a", 1, source_ids=[])
    downstream = _record_with_sources("a", 2, source_ids=["a-1"])
    pol = _pol("p1", "a", verdict="rewrite", target_action_id="a-2")
    # An unrelated third action should not enter the DAG.
    unrelated = _record_with_sources("a", 3, source_ids=[])
    log = [upstream, downstream, pol, unrelated]
    dag = builder.build(action_log=log)

    node_ids = {n["id"] for n in dag["nodes"]}
    assert "a-2" in node_ids  # L0 target
    assert "a-1" in node_ids  # L1 ancestor via source_action_ids
    assert "p1" in node_ids  # policy annotation
    assert "a-3" not in node_ids
    edges = {(e["src"], e["dst"], e["label"]) for e in dag["edges"]}
    assert ("a-2", "a-1", "L1") in edges
    assert ("a-2", "p1", "policy") in edges


def test_transitive_attribution_via_source_ids() -> None:
    """Chain: L0 target ← a-2 ← a-1 via source_ids (backward walk)."""

    builder = AttributionGraphBuilder(cascade_window=0)
    root = _record_with_sources("a", 1, source_ids=[])
    middle = _record_with_sources("a", 2, source_ids=["a-1"])
    target = _record_with_sources("a", 3, source_ids=["a-2"])
    pol = _pol("p1", "a", verdict="rewrite", target_action_id="a-3")
    log = [root, middle, target, pol]
    dag = builder.build(action_log=log)
    node_ids = {n["id"] for n in dag["nodes"]}
    assert {"a-3", "a-2", "a-1", "p1"} <= node_ids


def test_fallback_to_proximity_when_no_source_ids():
    """Backward compat: records lacking source_action_ids use proximity heuristic."""
    builder = AttributionGraphBuilder(cascade_window=3)
    # No source_ids on any record -> fallback path
    log = [
        _pol("p1", "a", verdict="rewrite"),
        _msg("m1", "a"),
        _msg("m2", "a"),
    ]
    dag = builder.build(action_log=log)
    # Existing proximity behavior
    edges = {(e["src"], e["dst"], e["label"]) for e in dag["edges"]}
    assert ("p1", "m1", "L1") in edges
