"""Tests for the Phase-5 evaluation_criteria scorer.

Covers:

- Required action dispatched with matching compare_args → pass.
- Required action dispatched with mismatched compare_args → fail.
- Required action missing entirely → fail.
- Must-say strings present → pass.
- Must-say strings missing → fail.
- env_assertions are recorded as deferred, not gated.
- An empty evaluation_criteria block yields task_success=False
  (no checks means we cannot certify the task).
"""
from __future__ import annotations

from typing import Any

import pytest

from clawsocialarena.orchestrator.phase5_env_assertions import (
    evaluate_evaluation_criteria,
)
from clawsocialarena.scenario.models import GTBundle
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


def _action(
    *,
    agent_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    idx: int = 1,
) -> ActionRecord:
    return ActionRecord(
        action_id=f"act-{idx:03d}",
        prev_hash="GENESIS" if idx == 1 else f"hash-{idx-1:03d}",
        agent_id=agent_id,
        action_type=ActionType.TOOL_CALL,
        timestamp="2026-05-11T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={"tool_name": tool_name, "arguments": arguments},
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def _action_with_observation(
    *,
    agent_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    idx_call: int = 1,
    idx_obs: int = 2,
    error: bool = False,
) -> list[ActionRecord]:
    """Build the canonical pair: TOOL_CALL + matching TOOL_OBSERVATION_RETURN.

    R-B 2's env_assertions evaluator only credits a canonical
    action when an observation follows the call (so failed
    dispatches do not silently count).
    """
    call = _action(
        agent_id=agent_id,
        tool_name=tool_name,
        arguments=arguments,
        idx=idx_call,
    )
    observation_payload: dict[str, Any] = {
        "tool_name": tool_name,
        "tool_call_action_id": call.action_id,
        "observation": "{}",
    }
    if error:
        observation_payload["error"] = "synthetic_failure"
    obs = ActionRecord(
        action_id=f"act-{idx_obs:03d}",
        prev_hash=call.action_id,
        agent_id=agent_id,
        action_type=ActionType.TOOL_OBSERVATION_RETURN,
        timestamp="2026-05-11T00:00:01Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload=observation_payload,
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )
    return [call, obs]


def _gt_with_criteria(
    *,
    actions: list[dict[str, Any]],
    communicate_info: list[dict[str, Any]],
    env_assertions: list[dict[str, Any]] | None = None,
    canonical_action_stream: list[dict[str, Any]] | None = None,
) -> tuple[GTBundle, dict[str, Any]]:
    raw = {
        "scenario_id": "phase5_env_test",
        "canonical_action_stream": canonical_action_stream or [],
        "terminal_predicate": {"type": "none"},
    }
    bundle = GTBundle.model_validate(raw)
    criteria = {
        "actions": actions,
        "communicate_info": communicate_info,
        "env_assertions": env_assertions or [],
    }
    return bundle, criteria


def test_actions_and_communicate_both_pass() -> None:
    gt, criteria = _gt_with_criteria(
        actions=[
            {
                "agent_id": "alice_assistant",
                "tool_name": "exchange_item",
                "compare_args": ["order_id"],
            }
        ],
        communicate_info=[
            {
                "agent_id": "alice_assistant",
                "must_say": ["#W2611340", "exchange confirmed"],
            }
        ],
        canonical_action_stream=[
            {
                "agent_id": "alice_assistant",
                "tool_name": "exchange_item",
                "arguments": {"order_id": "#W2611340"},
            }
        ],
    )
    log = _action_with_observation(
        agent_id="alice_assistant",
        tool_name="exchange_item",
        arguments={"order_id": "#W2611340"},
    )
    messages = [
        {
            "from": "alice_assistant",
            "to": "bob",
            "content": "Done -- #W2611340 exchange confirmed.",
        },
    ]
    result = evaluate_evaluation_criteria(
        gt_bundle=gt,
        evaluation_criteria_override=criteria,
        action_log=log,
        outbound_messages=messages,
    )
    assert result.task_success is True
    assert result.action_passes
    assert not result.action_failures
    assert result.communicate_passes
    assert not result.communicate_failures
    assert "exchange_item" in result.canonical_actions_dispatched


def test_action_with_arg_mismatch_fails() -> None:
    gt, criteria = _gt_with_criteria(
        actions=[
            {
                "agent_id": "alice",
                "tool_name": "exchange_item",
                "compare_args": ["order_id"],
            }
        ],
        communicate_info=[],
        canonical_action_stream=[
            {
                "agent_id": "alice",
                "tool_name": "exchange_item",
                "arguments": {"order_id": "#W2611340"},
            }
        ],
    )
    log = _action_with_observation(
        agent_id="alice",
        tool_name="exchange_item",
        arguments={"order_id": "#WRONG_ID"},
    )
    result = evaluate_evaluation_criteria(
        gt_bundle=gt, evaluation_criteria_override=criteria, action_log=log, outbound_messages=[]
    )
    assert result.task_success is False
    assert result.action_failures
    mismatch = result.action_failures[0]["first_mismatch"]
    assert mismatch["key"] == "order_id"


def test_missing_action_fails() -> None:
    gt, criteria = _gt_with_criteria(
        actions=[
            {
                "agent_id": "alice",
                "tool_name": "exchange_item",
                "compare_args": ["order_id"],
            }
        ],
        communicate_info=[],
    )
    result = evaluate_evaluation_criteria(
        gt_bundle=gt, evaluation_criteria_override=criteria, action_log=[], outbound_messages=[]
    )
    assert result.task_success is False
    assert result.action_failures[0]["reason"] == "no_call_dispatched"


def test_missing_must_say_logs_failure_but_does_not_gate_task_success() -> None:
    """Stream A redesign: ``communicate_info`` is captured as a logged
    social metric but no longer gates ``task_success``. A bundle that
    declares only ``communicate_info`` (no ``actions``, no
    ``env_assertions``) still produces ``task_success=False`` because
    ``has_any_check`` requires at least one gating check; the rationale
    has shifted from "must_say missing" to "no gating check declared".
    """
    gt, criteria = _gt_with_criteria(
        actions=[],
        communicate_info=[
            {
                "agent_id": "alice",
                "must_say": ["confirmation_token_42"],
            }
        ],
    )
    result = evaluate_evaluation_criteria(
        gt_bundle=gt,
        evaluation_criteria_override=criteria,
        action_log=[],
        outbound_messages=[
            {"from": "alice", "to": "bob", "content": "Hello world"}
        ],
    )
    assert result.task_success is False
    assert result.communicate_failures
    assert "confirmation_token_42" in result.communicate_failures[0]["missing"]


def test_env_assertions_now_gate_task_success_via_predicate_registry() -> None:
    gt, criteria = _gt_with_criteria(
        actions=[],
        communicate_info=[
            {"agent_id": "alice", "must_say": ["ok"]}
        ],
        env_assertions=[
            {
                "predicate": "household_order_finalized_for",
                "args": {"order_id": "#W2611340", "household_id": "HH-7"},
            },
            {
                "predicate": "household_payment_authorized_by",
                "args": {"order_id": "#W2611340", "expected_authorizer_id": "alice"},
            },
        ],
    )
    result = evaluate_evaluation_criteria(
        gt_bundle=gt,
        evaluation_criteria_override=criteria,
        action_log=[],
        outbound_messages=[
            {"from": "alice", "to": "bob", "content": "ok, all done"}
        ],
    )
    # Stream A redesign: predicates now GATE task_success rather than
    # being deferred. Without a ``resources_dir`` they cannot evaluate,
    # so each declared predicate lands in ``predicate_failures`` with
    # reason="resources_dir_unavailable" and task_success is False.
    # ``communicate_info`` is logged but no longer gates the verdict.
    assert result.task_success is False
    assert len(result.predicate_failures) == 2
    predicates = {item["predicate"] for item in result.predicate_failures}
    assert predicates == {
        "household_order_finalized_for",
        "household_payment_authorized_by",
    }
    assert all(
        item["reason"] == "resources_dir_unavailable"
        for item in result.predicate_failures
    )
    # communicate_info still produces pass/fail records but does not gate.
    assert len(result.communicate_passes) == 1


def test_tool_call_without_observation_does_not_credit() -> None:
    """Codex R-B 2 substrate review blocker (1): the agent loop
    appends the TOOL_CALL row before mcp_host.dispatch executes,
    so a failed dispatch leaves a logged call with no matching
    observation. The env_assertions evaluator must NOT credit
    that as a canonical action; otherwise task_success silently
    overcounts.
    """
    gt, criteria = _gt_with_criteria(
        actions=[
            {
                "agent_id": "alice",
                "tool_name": "exchange_item",
                "compare_args": ["order_id"],
            }
        ],
        communicate_info=[],
        canonical_action_stream=[
            {
                "agent_id": "alice",
                "tool_name": "exchange_item",
                "arguments": {"order_id": "#W2611340"},
            }
        ],
    )
    # Only the TOOL_CALL row is in the log; no matching
    # TOOL_OBSERVATION_RETURN follows.
    log = [
        _action(
            agent_id="alice",
            tool_name="exchange_item",
            arguments={"order_id": "#W2611340"},
        )
    ]
    result = evaluate_evaluation_criteria(
        gt_bundle=gt,
        evaluation_criteria_override=criteria,
        action_log=log,
        outbound_messages=[],
    )
    assert result.task_success is False
    assert result.action_failures
    assert result.action_failures[0]["reason"] == "no_call_dispatched"


def test_tool_observation_with_error_does_not_credit() -> None:
    """Observations marked with an ``error`` field indicate a
    dispatch that completed but reported failure. These should
    also not credit the canonical action.
    """
    gt, criteria = _gt_with_criteria(
        actions=[
            {
                "agent_id": "alice",
                "tool_name": "exchange_item",
                "compare_args": ["order_id"],
            }
        ],
        communicate_info=[],
        canonical_action_stream=[
            {
                "agent_id": "alice",
                "tool_name": "exchange_item",
                "arguments": {"order_id": "#W2611340"},
            }
        ],
    )
    log = _action_with_observation(
        agent_id="alice",
        tool_name="exchange_item",
        arguments={"order_id": "#W2611340"},
        error=True,
    )
    result = evaluate_evaluation_criteria(
        gt_bundle=gt,
        evaluation_criteria_override=criteria,
        action_log=log,
        outbound_messages=[],
    )
    assert result.task_success is False


def test_empty_evaluation_criteria_yields_false() -> None:
    gt, criteria = _gt_with_criteria(actions=[], communicate_info=[])
    result = evaluate_evaluation_criteria(
        gt_bundle=gt, evaluation_criteria_override=criteria, action_log=[], outbound_messages=[]
    )
    assert result.task_success is False
    assert result.diagnostics["has_any_check"] is False


def _seed_marble_research_sqlite(
    resources_dir, *, sections: dict, citations: list, approvals: dict
) -> None:
    """Write a minimal ``proposals`` row under one PI's sqlite so the
    EnvState builder picks it up and the predicates can score it.
    """
    import json
    import sqlite3
    db_dir = resources_dir / "pis" / "alice" / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / "personal.sqlite"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE proposals (
                proposal_id TEXT PRIMARY KEY,
                sections TEXT NOT NULL,
                citations TEXT NOT NULL,
                approvals TEXT NOT NULL,
                finalized INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "INSERT INTO proposals VALUES (?, ?, ?, ?, ?)",
            (
                "PROP-7",
                json.dumps(sections),
                json.dumps(citations),
                json.dumps(approvals),
                0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_predicate_passes_when_db_state_matches(tmp_path) -> None:
    """When the resources sqlite has a proposal with all 5Q sections
    filled in and every citation approved, both marble_research
    predicates pass and ``task_success`` becomes True (combined with
    a matching canonical action).
    """
    resources_dir = tmp_path / "resources"
    _seed_marble_research_sqlite(
        resources_dir,
        sections={
            "problem": "p",
            "importance": "i",
            "difficulty": "d",
            "gap": "g",
            "approach": "a",
        },
        citations=[
            {"kind": "unpublished_result", "result_id": "UR-x", "owner_id": "bob"}
        ],
        approvals={"UR-x": True},
    )
    gt, criteria = _gt_with_criteria(
        actions=[
            {"agent_id": "alice", "tool_name": "finalize_proposal", "compare_args": ["proposal_id"]}
        ],
        communicate_info=[],
        env_assertions=[
            {"predicate": "proposal_has_complete_5q", "args": {"proposal_id": "PROP-7"}},
            {"predicate": "proposal_citations_authorized", "args": {"proposal_id": "PROP-7"}},
        ],
        canonical_action_stream=[
            {
                "agent_id": "alice",
                "tool_name": "finalize_proposal",
                "arguments": {"proposal_id": "PROP-7", "finalizer_id": "alice"},
            }
        ],
    )
    log = _action_with_observation(
        agent_id="alice",
        tool_name="finalize_proposal",
        arguments={"proposal_id": "PROP-7", "finalizer_id": "alice"},
    )
    result = evaluate_evaluation_criteria(
        gt_bundle=gt,
        evaluation_criteria_override=criteria,
        action_log=log,
        outbound_messages=[],
        resources_dir=resources_dir,
        family_id="marble_research",
    )
    assert result.task_success is True
    assert len(result.predicate_passes) == 2
    assert result.predicate_failures == []


def test_predicate_fails_when_db_state_missing(tmp_path) -> None:
    """When required state is missing from the sqlite (no proposal
    inserted), the predicates return ``proposal_not_found`` and
    ``task_success`` is False even when the canonical action was
    dispatched correctly.
    """
    resources_dir = tmp_path / "resources"
    # Create the directory + an empty proposals table.
    db_dir = resources_dir / "pis" / "alice" / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    import sqlite3
    conn = sqlite3.connect(db_dir / "personal.sqlite")
    try:
        conn.execute(
            "CREATE TABLE proposals (proposal_id TEXT PRIMARY KEY, sections TEXT, citations TEXT, approvals TEXT, finalized INTEGER)"
        )
        conn.commit()
    finally:
        conn.close()
    gt, criteria = _gt_with_criteria(
        actions=[
            {"agent_id": "alice", "tool_name": "finalize_proposal", "compare_args": ["proposal_id"]}
        ],
        communicate_info=[],
        env_assertions=[
            {"predicate": "proposal_has_complete_5q", "args": {"proposal_id": "PROP-7"}},
        ],
        canonical_action_stream=[
            {
                "agent_id": "alice",
                "tool_name": "finalize_proposal",
                "arguments": {"proposal_id": "PROP-7", "finalizer_id": "alice"},
            }
        ],
    )
    log = _action_with_observation(
        agent_id="alice",
        tool_name="finalize_proposal",
        arguments={"proposal_id": "PROP-7", "finalizer_id": "alice"},
    )
    result = evaluate_evaluation_criteria(
        gt_bundle=gt,
        evaluation_criteria_override=criteria,
        action_log=log,
        outbound_messages=[],
        resources_dir=resources_dir,
        family_id="marble_research",
    )
    assert result.task_success is False
    assert len(result.predicate_failures) == 1
    assert result.predicate_failures[0]["reason"] == "proposal_not_found"


def test_unknown_predicate_lands_in_failures() -> None:
    """An env_assertion naming a predicate the family registry does
    not know about lands in ``predicate_failures`` rather than
    silently passing the task.
    """
    gt, criteria = _gt_with_criteria(
        actions=[],
        communicate_info=[],
        env_assertions=[
            {"predicate": "this_predicate_does_not_exist", "args": {"x": 1}},
        ],
    )
    result = evaluate_evaluation_criteria(
        gt_bundle=gt,
        evaluation_criteria_override=criteria,
        action_log=[],
        outbound_messages=[],
        resources_dir="/nonexistent",
        family_id="marble_research",
    )
    assert result.task_success is False
    assert len(result.predicate_failures) == 1
    assert result.predicate_failures[0]["reason"] == "predicate_not_registered"
