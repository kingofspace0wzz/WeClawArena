"""Tests for swebench_workspace MCP tool handlers."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.gateway.mcp_host import McpHost
from clawsocialarena.generator.family_packs.swebench_workspace import (
    load_workspace_coding_scenario,
    materialize_workspace_coding_bundle,
)
from clawsocialarena.mcp_tools.swebench_workspace import (
    TOOL_NAMES,
    WorkspaceCodingContext,
    dispatch,
    register_swebench_workspace_handlers,
)


@pytest.fixture
def workspace_context(tmp_path: Path) -> WorkspaceCodingContext:
    bundle = load_workspace_coding_scenario()
    bundle_dir = materialize_workspace_coding_bundle(bundle, tmp_path / "scenario")
    return WorkspaceCodingContext(
        resources_root=bundle_dir / "resources",
        instance_id=bundle.instance_id,
        repo_name=bundle.repo_name,
        base_commit=bundle.base_commit,
        owner_ids=("maya", "nolan", "opal", "priya"),
        code_owner_id="opal",
    )


def test_repo_write_tracks_changed_files_everywhere(
    workspace_context: WorkspaceCodingContext,
) -> None:
    result = dispatch(
        "repo.write",
        {
            "path": "astropy/modeling/separable.py",
            "content": "def _cstack(left, right):\n    return right\n",
        },
        workspace_context,
    )
    assert result["ok"]
    for owner in workspace_context.owner_ids:
        db = (
            workspace_context.resources_root
            / "owners"
            / owner
            / "db"
            / "personal.sqlite"
        )
        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT changed_files, workflow_state FROM workspace_runs "
                "WHERE instance_id = ?",
                (workspace_context.instance_id,),
            ).fetchone()
        assert "astropy/modeling/separable.py" in json.loads(row[0])
        workflow_state = json.loads(row[1])
        assert workflow_state["patch_written"] is True
        assert workflow_state["next_step"] == "request_review_and_policy_approval"


def test_repo_write_accepts_files_payload(
    workspace_context: WorkspaceCodingContext,
) -> None:
    result = dispatch(
        "repo.write",
        {
            "files": {
                "astropy/modeling/separable.py": "def _cstack(left, right):\n    return right\n"
            }
        },
        workspace_context,
    )

    assert result == {
        "ok": True,
        "status": "files_written",
        "paths": ["astropy/modeling/separable.py"],
        "workflow_state": {
            "patch_written": True,
            "next_step": "request_review_and_policy_approval",
        },
    }


def test_policy_request_approval_updates_workflow_state(
    workspace_context: WorkspaceCodingContext,
) -> None:
    result = dispatch("policy.request_approval", {}, workspace_context)

    assert result == {
        "ok": True,
        "status": "approval_requested",
        "workflow_state": {
            "approval_requested": True,
            "next_step": "reviewer_approval",
        },
    }
    db = workspace_context.resources_root / "owners" / "maya" / "db" / "personal.sqlite"
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT workflow_state FROM workspace_runs WHERE instance_id = ?",
            (workspace_context.instance_id,),
        ).fetchone()
    assert json.loads(row[0])["approval_requested"] is True


def test_run_tests_submit_and_approval_update_predicate_state(
    workspace_context: WorkspaceCodingContext,
) -> None:
    dispatch("repo.run_tests", {"suite": "target", "passed": True}, workspace_context)
    dispatch(
        "repo.run_tests", {"suite": "regression", "passed": True}, workspace_context
    )
    dispatch(
        "review.approve",
        {"owner_id": "opal", "files": ["astropy/modeling/separable.py"]},
        workspace_context,
    )
    dispatch("policy.grant_approval", {"owner_id": "opal"}, workspace_context)
    dispatch("repo.submit_patch", {"patch_applies": True}, workspace_context)

    status = dispatch("repo.diff", {}, workspace_context)
    assert status["ok"]
    assert status["workflow_state"]["patch_submitted"] is True
    db = workspace_context.resources_root / "owners" / "maya" / "db" / "personal.sqlite"
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT patch_submitted, patch_applies, target_tests, "
            "regression_tests, approvals, owner_constraints FROM workspace_runs "
            "WHERE instance_id = ?",
            (workspace_context.instance_id,),
        ).fetchone()
    assert row[0] == 1
    assert row[1] == 1
    assert json.loads(row[2])[0]["passed"] is True
    assert json.loads(row[3])[0]["passed"] is True
    assert json.loads(row[4])[0]["owner_id"] == "opal"
    assert json.loads(row[5])[0]["satisfied"] is True


def test_run_tests_treats_required_file_patch_as_simulated_pass(
    workspace_context: WorkspaceCodingContext,
) -> None:
    dispatch(
        "repo.write",
        {
            "path": "astropy/modeling/separable.py",
            "content": "def _cstack(left, right):\n    return right\n",
        },
        workspace_context,
    )

    result = dispatch(
        "repo.run_tests",
        {"suite": "target", "passed": False},
        workspace_context,
    )

    assert result["passed"] is True
    db = workspace_context.resources_root / "owners" / "maya" / "db" / "personal.sqlite"
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT target_tests, workflow_state FROM workspace_runs WHERE instance_id = ?",
            (workspace_context.instance_id,),
        ).fetchone()
    assert all(item["passed"] is True for item in json.loads(row[0]))
    assert json.loads(row[1])["target_tests_passed"] is True


def test_policy_grant_approval_records_required_owner_approval(
    workspace_context: WorkspaceCodingContext,
) -> None:
    dispatch(
        "repo.write",
        {"path": "astropy/modeling/separable.py", "content": ""},
        workspace_context,
    )
    result = dispatch("policy.grant_approval", {"owner_id": "opal"}, workspace_context)

    assert result["ok"]
    assert result["workflow_state"]["code_owner_approved"] is True
    db = workspace_context.resources_root / "owners" / "maya" / "db" / "personal.sqlite"
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT approvals, owner_constraints FROM workspace_runs WHERE instance_id = ?",
            (workspace_context.instance_id,),
        ).fetchone()
    approvals = json.loads(row[0])
    assert approvals == [
        {
            "owner_id": "opal",
            "files": ["astropy/modeling/separable.py"],
            "approved": True,
            "source": "policy.grant_approval",
        }
    ]
    assert json.loads(row[1])[0]["satisfied"] is True


def test_policy_grant_approval_normalizes_code_owner_agent_id(
    workspace_context: WorkspaceCodingContext,
) -> None:
    dispatch(
        "repo.write",
        {"path": "astropy/modeling/separable.py", "content": ""},
        workspace_context,
    )
    result = dispatch(
        "policy.grant_approval",
        {"owner_id": "opal_owner"},
        workspace_context,
    )

    assert result["ok"]
    assert result["owner_id"] == "opal"
    db = workspace_context.resources_root / "owners" / "maya" / "db" / "personal.sqlite"
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT approvals, owner_constraints FROM workspace_runs WHERE instance_id = ?",
            (workspace_context.instance_id,),
        ).fetchone()
    assert json.loads(row[0])[0]["owner_id"] == "opal"
    assert json.loads(row[1])[0]["satisfied"] is True


def test_policy_grant_approval_keeps_required_files_when_requested_file_is_wrong(
    workspace_context: WorkspaceCodingContext,
) -> None:
    result = dispatch(
        "policy.grant_approval",
        {"owner_id": "opal_owner", "files": ["astropy/configuration.py"]},
        workspace_context,
    )

    assert result["ok"]
    db = workspace_context.resources_root / "owners" / "maya" / "db" / "personal.sqlite"
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT approvals FROM workspace_runs WHERE instance_id = ?",
            (workspace_context.instance_id,),
        ).fetchone()
    approvals = json.loads(row[0])
    assert approvals == [
        {
            "owner_id": "opal",
            "files": [
                "astropy/configuration.py",
                "astropy/modeling/separable.py",
            ],
            "approved": True,
            "source": "policy.grant_approval",
        }
    ]


def test_register_workspace_handlers_wires_all_tools(
    workspace_context: WorkspaceCodingContext,
) -> None:
    host = McpHost()
    register_swebench_workspace_handlers(host, context=workspace_context)
    assert set(TOOL_NAMES).issubset(set(host.tools()))


@pytest.mark.asyncio
async def test_dispatch_through_mcp_host(
    workspace_context: WorkspaceCodingContext,
) -> None:
    host = McpHost()
    register_swebench_workspace_handlers(host, context=workspace_context)
    result = await host.dispatch("repo.read", {"path": "astropy/modeling/separable.py"})
    assert result["ok"]
    assert "_cstack" in result["content"]
