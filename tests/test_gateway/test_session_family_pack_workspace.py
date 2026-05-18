"""Session.build wires swebench_workspace handlers automatically."""

from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.gateway.session import Session
from clawsocialarena.generator.family_packs.swebench_workspace import (
    load_workspace_coding_scenario,
    materialize_workspace_coding_bundle,
)
from clawsocialarena.mcp_tools.swebench_workspace import TOOL_NAMES
from clawsocialarena.types import AuditCondition


@pytest.fixture
def materialized_bundle_dir(tmp_path: Path) -> Path:
    bundle = load_workspace_coding_scenario()
    return materialize_workspace_coding_bundle(bundle, tmp_path / "scenario")


def test_session_build_baseline_registers_workspace_handlers(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    session = Session.build(
        scenario_id="swebench_workspace_smoke",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",
        resource_root=materialized_bundle_dir / "resources",
        family_id="swebench_workspace",
        family_pack_context={
            "instance_id": "astropy__astropy-12907",
            "repo_name": "astropy/astropy",
            "base_commit": "d16bfe05a744909de4b27f5875fe0d4ed41ce607",
            "implementer_owner_id": "maya",
            "reviewer_owner_id": "nolan",
            "code_owner_id": "opal",
            "ci_owner_id": "priya",
        },
    )
    assert set(TOOL_NAMES).issubset(set(session.mcp_host.tools()))


@pytest.mark.asyncio
async def test_session_built_workspace_handlers_dispatch_against_real_repo(
    materialized_bundle_dir: Path,
    tmp_path: Path,
) -> None:
    session = Session.build(
        scenario_id="dispatch_smoke_workspace",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "action_log.db",
        resource_root=materialized_bundle_dir / "resources",
        work_dir=tmp_path,
        family_id="swebench_workspace",
        family_pack_context={
            "instance_id": "astropy__astropy-12907",
            "repo_name": "astropy/astropy",
            "base_commit": "d16bfe05a744909de4b27f5875fe0d4ed41ce607",
            "implementer_owner_id": "maya",
            "reviewer_owner_id": "nolan",
            "code_owner_id": "opal",
            "ci_owner_id": "priya",
        },
    )
    result = await session.mcp_host.dispatch(
        "repo.read",
        {"path": "astropy/modeling/separable.py"},
    )
    assert result["ok"]
    assert "_cstack" in result["content"]


@pytest.mark.asyncio
async def test_session_build_passes_workspace_v2_context(
    tmp_path: Path,
) -> None:
    bundle = load_workspace_coding_scenario(workspace_substrate_version="v2")
    materialized_bundle_dir = materialize_workspace_coding_bundle(
        bundle,
        tmp_path / "scenario",
    )
    session = Session.build(
        scenario_id="dispatch_smoke_workspace_v2",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "action_log.db",
        resource_root=materialized_bundle_dir / "resources",
        work_dir=tmp_path,
        family_id="swebench_workspace",
        family_pack_context={
            "instance_id": bundle.instance_id,
            "repo_name": bundle.repo_name,
            "base_commit": bundle.base_commit,
            "implementer_owner_id": "maya",
            "reviewer_owner_id": "nolan",
            "code_owner_id": "opal",
            "ci_owner_id": "priya",
            "workspace_substrate_version": "v2",
        },
    )

    result = await session.mcp_host.dispatch(
        "repo.submit_patch",
        {"patch_applies": True},
    )

    assert result["ok"] is False
    assert result["error"] == "evidence_chain_incomplete"
    assert result["missing"] == [
        "required_files_changed",
        "review_decision_recorded",
        "owner_approval_recorded",
        "target_tests_recorded",
        "regression_tests_recorded",
        "implementer_repro_read",
        "implementer_patch_finding_queried",
        "reviewer_checklist_read",
        "code_owner_policy_read",
        "code_owner_scope_queried",
        "ci_target_plan_read",
        "ci_regression_plan_read",
    ]
