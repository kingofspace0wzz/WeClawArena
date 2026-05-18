"""End-to-end env assertion smoke test for swebench_workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from clawsocialarena.generator.family_packs.swebench_workspace import (
    load_workspace_coding_scenario,
    materialize_workspace_coding_bundle,
)
from clawsocialarena.mcp_tools.swebench_workspace import (
    WorkspaceCodingContext,
    dispatch,
)
from clawsocialarena.orchestrator.phase5_env_assertions import evaluate_from_bundle_dir
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


def _action_pair(
    *,
    agent_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    idx: int,
) -> list[ActionRecord]:
    call = ActionRecord(
        action_id=f"act-{idx:03d}",
        prev_hash="GENESIS" if idx == 1 else f"hash-{idx - 1:03d}",
        agent_id=agent_id,
        action_type=ActionType.TOOL_CALL,
        timestamp="2026-05-14T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.NEGOTIATION,
        payload={"tool_name": tool_name, "arguments": arguments},
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )
    obs = ActionRecord(
        action_id=f"act-{idx + 1:03d}",
        prev_hash=call.action_id,
        agent_id=agent_id,
        action_type=ActionType.TOOL_OBSERVATION_RETURN,
        timestamp="2026-05-14T00:00:01Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.NEGOTIATION,
        payload={
            "tool_name": tool_name,
            "tool_call_action_id": call.action_id,
            "observation": "{}",
        },
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )
    return [call, obs]


def test_swebench_workspace_env_assertions_gate_task_success(tmp_path: Path) -> None:
    bundle = load_workspace_coding_scenario()
    bundle_dir = materialize_workspace_coding_bundle(bundle, tmp_path / "scenario")
    context = WorkspaceCodingContext(
        resources_root=bundle_dir / "resources",
        instance_id=bundle.instance_id,
        repo_name=bundle.repo_name,
        base_commit=bundle.base_commit,
        owner_ids=("maya", "nolan", "opal", "priya"),
        code_owner_id="opal",
    )
    dispatch(
        "repo.write",
        {
            "path": "astropy/modeling/separable.py",
            "content": "def _cstack(left, right):\n    return right\n",
        },
        context,
    )
    dispatch("repo.run_tests", {"suite": "target", "passed": True}, context)
    dispatch("repo.run_tests", {"suite": "regression", "passed": True}, context)
    dispatch(
        "review.approve",
        {"owner_id": "opal", "files": ["astropy/modeling/separable.py"]},
        context,
    )
    dispatch("policy.grant_approval", {"owner_id": "opal"}, context)
    dispatch("repo.submit_patch", {"patch_applies": True}, context)

    action_log = [
        *_action_pair(
            agent_id="maya_engineer",
            tool_name="repo.write",
            arguments={"instance_id": bundle.instance_id, "suite": "target"},
            idx=1,
        ),
        *_action_pair(
            agent_id="priya_ci",
            tool_name="repo.run_tests",
            arguments={"instance_id": bundle.instance_id, "suite": "target"},
            idx=3,
        ),
        *_action_pair(
            agent_id="priya_ci",
            tool_name="repo.submit_patch",
            arguments={"instance_id": bundle.instance_id},
            idx=5,
        ),
        *_action_pair(
            agent_id="nolan_reviewer",
            tool_name="review.approve",
            arguments={"instance_id": bundle.instance_id},
            idx=7,
        ),
        *_action_pair(
            agent_id="opal_owner",
            tool_name="policy.grant_approval",
            arguments={"instance_id": bundle.instance_id},
            idx=9,
        ),
    ]
    result = evaluate_from_bundle_dir(
        bundle_dir=bundle_dir,
        action_log=action_log,
        outbound_messages=[],
        family_id="swebench_workspace",
    )
    assert result.task_success is True
    assert len(result.predicate_passes) == 8
    assert result.predicate_failures == []


def test_swebench_workspace_v2_env_assertions_require_evidence_chain(
    tmp_path: Path,
) -> None:
    bundle = load_workspace_coding_scenario(workspace_substrate_version="v2")
    bundle_dir = materialize_workspace_coding_bundle(bundle, tmp_path / "scenario")
    context = WorkspaceCodingContext(
        resources_root=bundle_dir / "resources",
        instance_id=bundle.instance_id,
        repo_name=bundle.repo_name,
        base_commit=bundle.base_commit,
        owner_ids=("maya", "nolan", "opal", "priya"),
        code_owner_id="opal",
        workspace_substrate_version="v2",
    )

    dispatch(
        "repo.write",
        {
            "path": "astropy/modeling/separable.py",
            "content": "def _cstack(left, right):\n    return right\n",
        },
        context,
    )

    action_log = [
        *_action_pair(
            agent_id="maya_engineer",
            tool_name="repo.write",
            arguments={"instance_id": bundle.instance_id},
            idx=1,
        ),
    ]
    result = evaluate_from_bundle_dir(
        bundle_dir=bundle_dir,
        action_log=action_log,
        outbound_messages=[],
        family_id="swebench_workspace",
    )

    assert result.task_success is False
    failures = {item["predicate"]: item for item in result.predicate_failures}
    assert failures["evidence_chain_complete"]["reason"] == (
        "evidence_chain_incomplete"
    )
