from __future__ import annotations

from dataclasses import replace

import pytest

from clawsocialarena.generator.family_packs.swebench_workspace import (
    load_workspace_coding_scenario,
)
from clawsocialarena.generator.family_packs.swebench_workspace.v2_schema import (
    build_workspace_v2_evidence_bundle,
)


def test_v2_evidence_bundle_has_four_owned_ecosystems() -> None:
    bundle = load_workspace_coding_scenario(workspace_substrate_version="v2")

    evidence = build_workspace_v2_evidence_bundle(bundle)

    assert evidence.substrate_version == "v2"
    assert evidence.instance_id == bundle.instance_id
    assert evidence.repo_name == bundle.repo_name
    assert evidence.required_files == bundle.required_approval_files
    assert evidence.forbidden_files == bundle.forbidden_files
    assert set(evidence.owner_specs) == {"maya", "nolan", "opal", "priya"}
    assert evidence.owner_specs["maya"].role == "implementer"
    assert evidence.owner_specs["nolan"].role == "reviewer"
    assert evidence.owner_specs["opal"].role == "code_owner"
    assert evidence.owner_specs["priya"].role == "ci_owner"
    assert evidence.owner_specs["maya"].agent_id == "maya_engineer"
    assert evidence.owner_specs["nolan"].agent_id == "nolan_reviewer"
    assert evidence.owner_specs["opal"].agent_id == "opal_owner"
    assert evidence.owner_specs["priya"].agent_id == "priya_ci"
    assert "notes/repro.md" in evidence.owner_specs["maya"].files
    assert "review/checklist.md" in evidence.owner_specs["nolan"].files
    assert "ownership/approval_policy.md" in evidence.owner_specs["opal"].files
    assert "ci/regression_result.md" in evidence.owner_specs["priya"].files
    assert "target tests" in evidence.owner_specs["maya"].files["notes/repro.md"]
    assert (
        "review.approve" in evidence.owner_specs["nolan"].files["review/checklist.md"]
    )
    assert (
        bundle.owner_constraint_id
        in evidence.owner_specs["opal"].files["ownership/approval_policy.md"]
    )
    assert (
        "regression tests"
        in evidence.owner_specs["priya"].files["ci/regression_result.md"]
    )
    maya = evidence.owner_specs["maya"]
    opal = evidence.owner_specs["opal"]
    assert "resource_facts" in maya.sqlite_tables
    assert len(maya.sqlite_tables["resource_facts"]) >= 5
    assert any(
        row["fact_id"] == "implementer.required_file"
        and row["fact_value"] == bundle.required_approval_files[0]
        for row in maya.sqlite_tables["resource_facts"]
    )
    assert any(
        row["fact_id"] == "code_owner.constraint_id"
        and row["fact_value"] == bundle.owner_constraint_id
        for row in opal.sqlite_tables["resource_facts"]
    )
    assert bundle.instance_id in maya.files["notes/repro.md"]
    assert bundle.required_approval_files[0] in maya.files["notes/patch.md"]
    assert evidence.owner_specs["maya"].sqlite_tables["patch_findings"] == [
        {
            "finding_id": "finding-required-file",
            "file_path": bundle.required_approval_files[0],
            "finding": "Primary candidate file from reduced fixture.",
            "confidence": 0.85,
        }
    ]
    assert evidence.owner_specs["opal"].sqlite_tables["ownership_scope"] == [
        {
            "scope_id": "scope-required-files",
            "file_glob": bundle.required_approval_files[0],
            "owner_id": "opal",
            "role_id": "code_owner",
        }
    ]
    assert evidence.owner_specs["nolan"].sqlite_tables["review_decisions"] == []
    assert evidence.owner_specs["opal"].sqlite_tables["owner_approvals"] == []
    assert evidence.owner_specs["priya"].sqlite_tables["test_runs"] == []
    assert evidence.owner_specs["priya"].sqlite_tables["test_claims"] == []
    assert evidence.submission_requirements == {
        "patch_applies": True,
        "required_files_changed": True,
        "review_decision_recorded": True,
        "owner_approval_recorded": True,
        "target_tests_recorded": True,
        "regression_tests_recorded": True,
        "forbidden_files_unchanged": True,
    }


def test_v2_evidence_bundle_requires_agent_graph() -> None:
    bundle = load_workspace_coding_scenario(workspace_substrate_version="v2")
    scenario_without_graph = bundle.scenario.model_copy(update={"agent_graph": None})

    with pytest.raises(
        ValueError,
        match="workspace v2 evidence requires an agent graph",
    ):
        build_workspace_v2_evidence_bundle(
            replace(bundle, scenario=scenario_without_graph),
        )
