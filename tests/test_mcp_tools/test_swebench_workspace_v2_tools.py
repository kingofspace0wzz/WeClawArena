from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.generator.family_packs.swebench_workspace import (
    load_workspace_coding_scenario,
    materialize_workspace_coding_bundle,
)
from clawsocialarena.mcp_tools.swebench_workspace import (
    WorkspaceCodingContext,
    dispatch,
)


@pytest.fixture
def v2_context(tmp_path: Path) -> WorkspaceCodingContext:
    bundle = load_workspace_coding_scenario(workspace_substrate_version="v2")
    bundle_dir = materialize_workspace_coding_bundle(bundle, tmp_path / "scenario")
    return WorkspaceCodingContext(
        resources_root=bundle_dir / "resources",
        instance_id=bundle.instance_id,
        repo_name=bundle.repo_name,
        base_commit=bundle.base_commit,
        owner_ids=("maya", "nolan", "opal", "priya"),
        code_owner_id="opal",
        workspace_substrate_version="v2",
    )


def test_v2_submit_blocks_missing_evidence_chain(
    v2_context: WorkspaceCodingContext,
) -> None:
    result = dispatch("repo.submit_patch", {"patch_applies": True}, v2_context)

    assert result == {
        "ok": False,
        "error": "evidence_chain_incomplete",
        "missing": [
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
        ],
    }


def test_v2_run_tests_blocks_until_resource_evidence_is_recorded(
    v2_context: WorkspaceCodingContext,
) -> None:
    dispatch(
        "repo.write",
        {
            "path": "astropy/modeling/separable.py",
            "content": "def _cstack(left, right):\n    return right\n",
        },
        v2_context,
    )

    result = dispatch("repo.run_tests", {"suite": "target", "passed": True}, v2_context)

    assert result == {
        "ok": False,
        "error": "missing_resource_evidence",
        "missing": [
            "implementer_repro_read",
            "implementer_patch_finding_queried",
            "ci_target_plan_read",
        ],
    }


def test_v2_owned_resource_tools_accept_agent_ids(
    v2_context: WorkspaceCodingContext,
) -> None:
    checklist = dispatch(
        "read_owned_file",
        {"owner_id": "nolan_reviewer", "path": "review/checklist.md"},
        v2_context,
    )
    scope = dispatch(
        "query_owned_table",
        {"owner_id": "opal_owner", "table": "ownership_scope"},
        v2_context,
    )
    facts = dispatch(
        "query_owned_table",
        {"owner_id": "maya_engineer", "table": "resource_facts"},
        v2_context,
    )

    assert checklist["ok"] is True
    assert checklist["owner_id"] == "nolan"
    assert "review.approve" in checklist["content"]
    assert scope["ok"] is True
    assert scope["owner_id"] == "opal"
    assert scope["rows"][0]["file_glob"] == "astropy/modeling/separable.py"
    assert facts["ok"] is True
    assert any(row["fact_id"] == "implementer.required_file" for row in facts["rows"])


def test_v2_owned_resource_tools_accept_short_agent_aliases(tmp_path: Path) -> None:
    bundle = load_workspace_coding_scenario(
        workspace_substrate_version="v2",
        scenario_id="alias_case",
        seed_id="alias_case",
        instance_id="alias__case",
        implementer_id="engineer24",
        reviewer_id="reviewer24",
        code_owner_id="owner24",
        ci_owner_id="ci24",
        implementer_owner="engineer24_user",
        reviewer_owner="reviewer24_user",
        code_owner="owner24_user",
        ci_owner="ci24_user",
    )
    bundle_dir = materialize_workspace_coding_bundle(bundle, tmp_path / "scenario")
    context = WorkspaceCodingContext(
        resources_root=bundle_dir / "resources",
        instance_id=bundle.instance_id,
        repo_name=bundle.repo_name,
        base_commit=bundle.base_commit,
        owner_ids=(
            "engineer24_user",
            "reviewer24_user",
            "owner24_user",
            "ci24_user",
        ),
        code_owner_id="owner24_user",
        workspace_substrate_version="v2",
    )

    checklist = dispatch(
        "read_owned_file",
        {"owner_id": "reviewer24", "path": "review/checklist.md"},
        context,
    )
    scope = dispatch(
        "query_owned_table",
        {"owner_id": "owner24", "table": "ownership_scope"},
        context,
    )

    assert checklist["ok"] is True
    assert checklist["owner_id"] == "reviewer24_user"
    assert scope["ok"] is True
    assert scope["owner_id"] == "owner24_user"


def test_v2_review_owner_ci_evidence_allows_submit(
    v2_context: WorkspaceCodingContext,
) -> None:
    repro = dispatch(
        "read_owned_file",
        {"owner_id": "maya", "path": "notes/repro.md"},
        v2_context,
    )
    findings = dispatch(
        "query_owned_table",
        {"owner_id": "maya", "table": "patch_findings"},
        v2_context,
    )
    dispatch(
        "repo.write",
        {
            "path": "astropy/modeling/separable.py",
            "content": "def _cstack(left, right):\n    return right\n",
        },
        v2_context,
    )
    checklist = dispatch(
        "read_owned_file",
        {"owner_id": "nolan", "path": "review/checklist.md"},
        v2_context,
    )
    dispatch(
        "review.approve",
        {
            "owner_id": "nolan",
            "files": ["astropy/modeling/separable.py"],
            "rationale": "Scoped patch only changes the required file.",
        },
        v2_context,
    )
    approval_policy = dispatch(
        "read_owned_file",
        {"owner_id": "opal", "path": "ownership/approval_policy.md"},
        v2_context,
    )
    ownership_scope = dispatch(
        "query_owned_table",
        {"owner_id": "opal", "table": "ownership_scope"},
        v2_context,
    )
    dispatch(
        "policy.grant_approval",
        {"owner_id": "opal", "files": ["astropy/modeling/separable.py"]},
        v2_context,
    )
    target_plan = dispatch(
        "read_owned_file",
        {"owner_id": "priya", "path": "ci/target_result.md"},
        v2_context,
    )
    dispatch("repo.run_tests", {"suite": "target", "passed": True}, v2_context)
    regression_plan = dispatch(
        "read_owned_file",
        {"owner_id": "priya", "path": "ci/regression_result.md"},
        v2_context,
    )
    dispatch("repo.run_tests", {"suite": "regression", "passed": True}, v2_context)

    result = dispatch("repo.submit_patch", {"patch_applies": True}, v2_context)

    assert repro["ok"] is True
    assert findings["rows"][0]["file_path"] == "astropy/modeling/separable.py"
    assert checklist["ok"] is True
    assert approval_policy["ok"] is True
    assert ownership_scope["rows"][0]["owner_id"] == "opal"
    assert target_plan["ok"] is True
    assert regression_plan["ok"] is True
    assert result["ok"] is True
    assert result["status"] == "patch_submitted"
    db = v2_context.resources_root / "owners" / "maya" / "db" / "personal.sqlite"
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT evidence_chain FROM workspace_runs WHERE instance_id = ?",
            (v2_context.instance_id,),
        ).fetchone()
    evidence_chain = json.loads(row[0])
    assert evidence_chain["evidence_chain_complete"] is True
    assert evidence_chain["resource_evidence_complete"] is True
