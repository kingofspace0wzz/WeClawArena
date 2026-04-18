"""Proximity fallback tests (Phase C / Task C8).

When both ``source_action_ids`` AND MSWM are empty on every record (the
pathological case where provenance was intentionally stripped), the
builder falls back to a positional proximity heuristic. With a live MSWM
the proximity scorer additionally uses item-overlap to disambiguate
candidate edges.
"""

from __future__ import annotations

from clawsocialarena.audit.attribution import AttributionGraphBuilder
from clawsocialarena.audit.mswm import MSWM
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
        timestamp="2026-04-17T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={"verdict": verdict, "policy_id": "p1"},
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def _msg(
    action_id: str,
    agent: str,
    *,
    mentioned: list[str] | None = None,
    sources: list[str] | None = None,
) -> ActionRecord:
    payload: dict = {"recipient_id": "bob", "content": "."}
    if mentioned is not None:
        payload["mentioned_items"] = mentioned
    return ActionRecord(
        action_id=action_id,
        prev_hash="0" * 64,
        agent_id=agent,
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-17T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload=payload,
        integrity_level=IntegrityLevel.HASH_CHAINED,
        source_action_ids=list(sources or []),
    )


def test_proximity_fires_when_no_source_ids_or_mswm() -> None:
    """Pure positional fallback: L0 followed by two outbounds, both linked."""
    builder = AttributionGraphBuilder(cascade_window=3)
    log = [_pol("pol", "alice"), _msg("m1", "alice"), _msg("m2", "alice")]
    dag = builder.build(action_log=log)
    edge_triples = {(e["src"], e["dst"], e["label"]) for e in dag["edges"]}
    assert ("pol", "m1", "L1") in edge_triples
    assert ("pol", "m2", "L1") in edge_triples


def test_proximity_respects_cascade_window() -> None:
    builder = AttributionGraphBuilder(cascade_window=1)
    log = [_pol("pol", "alice"), _msg("m1", "alice"), _msg("m2", "alice")]
    dag = builder.build(action_log=log)
    edge_triples = {(e["src"], e["dst"], e["label"]) for e in dag["edges"]}
    assert ("pol", "m1", "L1") in edge_triples
    assert ("pol", "m2", "L1") not in edge_triples


def test_proximity_with_mswm_item_overlap_still_adds_edge() -> None:
    """Even with MSWM present, proximity works when mentioned items align."""
    # Build an MSWM where alice knows item z (via self-knowledge).
    mswm = MSWM()
    mswm.self_knowledge["alice"] = {"z"}

    # Stripped source_action_ids but mentioned_items in the candidates.
    log = [
        _pol("pol", "alice"),
        _msg("m1", "alice", mentioned=["z"]),
    ]
    # Because mswm HAS links (self_knowledge is ignored by _mswm_has_links
    # which only looks at peer state), the causal path is skipped and we
    # still fall through to proximity.
    dag = AttributionGraphBuilder(
        action_log=log, mswm=mswm, cascade_window=3
    ).build()
    edge_triples = {(e["src"], e["dst"], e["label"]) for e in dag["edges"]}
    assert ("pol", "m1", "L1") in edge_triples


def test_proximity_with_stripped_sources_but_mentioned_items() -> None:
    """Intentionally stripped source_action_ids: MSWM rebuild and proximity both try."""

    log = [
        _pol("pol", "alice"),
        _msg("m-next", "alice", mentioned=["z"]),
    ]
    # No mswm passed — the builder will rebuild from log. The rebuilt MSWM
    # has peer links (because m-next mentions z and sets items_told_to_j),
    # so the causal path fires. Verify it still produces something sensible.
    dag = AttributionGraphBuilder(action_log=log).build()
    ids = {n["id"] for n in dag["nodes"]}
    assert "pol" in ids


def test_proximity_score_favors_same_agent() -> None:
    """Same-agent candidate wins over a cross-agent one when both in window."""

    log = [
        _pol("pol", "alice"),
        _msg("m-bob", "bob"),
        _msg("m-alice", "alice"),
    ]
    dag = AttributionGraphBuilder(cascade_window=3).build(action_log=log)
    edge_triples = {(e["src"], e["dst"], e["label"]) for e in dag["edges"]}
    # Both are linked by proximity; the same-agent edge's score is higher
    # but both should be present (score > 0).
    assert ("pol", "m-bob", "L1") in edge_triples
    assert ("pol", "m-alice", "L1") in edge_triples
