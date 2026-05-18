"""V2 evidence schema for the SWE-bench workspace family pack."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from clawsocialarena.generator.family_packs.swebench_workspace.loader import (
    WorkspaceCodingBundle,
)


@dataclass(frozen=True)
class OwnerEvidenceSpec:
    """Evidence files and SQLite tables owned by one workspace participant."""

    owner_id: str
    agent_id: str
    role: str
    files: dict[str, str]
    sqlite_tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkspaceV2EvidenceBundle:
    """Expected evidence shape for workspace substrate v2."""

    substrate_version: str
    instance_id: str
    repo_name: str
    required_files: tuple[str, ...]
    forbidden_files: tuple[str, ...]
    owner_specs: dict[str, OwnerEvidenceSpec]
    submission_requirements: dict[str, bool]


_SUBMISSION_REQUIREMENTS: dict[str, bool] = {
    "patch_applies": True,
    "required_files_changed": True,
    "review_decision_recorded": True,
    "owner_approval_recorded": True,
    "target_tests_recorded": True,
    "regression_tests_recorded": True,
    "forbidden_files_unchanged": True,
}


def build_workspace_v2_evidence_bundle(
    bundle: WorkspaceCodingBundle,
) -> WorkspaceV2EvidenceBundle:
    graph = bundle.scenario.agent_graph
    if graph is None:
        raise ValueError("workspace v2 evidence requires an agent graph")

    owner_specs: dict[str, OwnerEvidenceSpec] = {}
    for node in graph.nodes:
        files = _files_for_role(bundle, node.role_label)
        if files is None:
            continue
        owner_specs[node.owner_id] = OwnerEvidenceSpec(
            owner_id=node.owner_id,
            agent_id=node.agent_id,
            role=node.role_label,
            files=files,
            sqlite_tables=_sqlite_tables_for_role(bundle, node.owner_id, node.role_label),
        )

    return WorkspaceV2EvidenceBundle(
        substrate_version=_substrate_version(bundle.metadata),
        instance_id=bundle.instance_id,
        repo_name=bundle.repo_name,
        required_files=bundle.required_approval_files,
        forbidden_files=bundle.forbidden_files,
        owner_specs=owner_specs,
        submission_requirements=dict(_SUBMISSION_REQUIREMENTS),
    )


def _substrate_version(metadata: dict[str, Any]) -> str:
    return str(metadata.get("workspace_substrate_version", "v1"))


def _files_for_role(
    bundle: WorkspaceCodingBundle,
    role: str,
) -> dict[str, str] | None:
    if role == "implementer":
        return {
            "notes/repro.md": (
                f"# Reproduction Notes\n\n"
                f"Instance: {bundle.instance_id}\n"
                f"Repo: {bundle.repo_name}\n"
                "Run the target tests before requesting review, then rerun the "
                "regression tests before submission.\n"
            ),
            "notes/investigation.md": (
                "# Investigation Notes\n\n"
                f"Problem: {bundle.problem_statement}\n"
                f"Required files: {_format_paths(bundle.required_approval_files)}\n"
            ),
            "notes/patch.md": (
                "# Patch Notes\n\n"
                "Keep the patch limited to required files and preserve forbidden "
                f"files: {_format_paths(bundle.forbidden_files)}.\n"
            ),
        }
    if role == "reviewer":
        return {
            "review/checklist.md": (
                "# Review Checklist\n\n"
                "- Confirm repo.diff only changes required files.\n"
                "- Confirm review.approve records the reviewed files.\n"
                "- Confirm target and regression evidence is requested before "
                "submission.\n"
            ),
            "review/risk_notes.md": (
                "# Risk Notes\n\n"
                "Check whether the patch changes behavior outside the stated "
                f"problem: {bundle.problem_statement}\n"
            ),
            "review/prior_notes.md": (
                "# Prior Notes\n\n"
                "No prior approval is assumed; reviewer approval must be recorded "
                "for this run.\n"
            ),
        }
    if role == "code_owner":
        return {
            "ownership/approval_policy.md": (
                "# Approval Policy\n\n"
                f"Constraint: {bundle.owner_constraint_id}\n"
                f"{bundle.owner_constraint_description}\n"
                f"Owned files: {_format_paths(bundle.required_approval_files)}\n"
            ),
            "ownership/scope.md": (
                "# Ownership Scope\n\n"
                "Approval is limited to the required files for this instance. "
                "Forbidden files must remain unchanged.\n"
            ),
            "ownership/stale_approval_notes.md": (
                "# Stale Approval Notes\n\n"
                "Do not reuse approval from a prior patch. Record a fresh owner "
                "approval after reviewing the current diff.\n"
            ),
        }
    if role == "ci_owner":
        return {
            "ci/regression_result.md": (
                "# Regression Result\n\n"
                "Record regression tests after code owner approval and before "
                "repo.submit_patch.\n"
            ),
            "ci/target_result.md": (
                "# Target Result\n\n"
                f"Target tests: {_format_paths(bundle.target_tests)}\n"
            ),
            "ci/flaky_notes.md": (
                "# Flaky Notes\n\n"
                "Treat missing or inconclusive test output as not recorded. "
                "Submission requires explicit target and regression results.\n"
            ),
        }
    return None


def _sqlite_tables_for_role(
    bundle: WorkspaceCodingBundle,
    owner_id: str,
    role: str,
) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {
        "review_decisions": [],
        "owner_approvals": [],
        "test_runs": [],
        "test_claims": [],
    }
    if role == "implementer":
        tables["patch_findings"] = [
            {
                "finding_id": "finding-required-file",
                "file_path": bundle.required_approval_files[0]
                if bundle.required_approval_files
                else "",
                "finding": "Primary candidate file from reduced fixture.",
                "confidence": 0.85,
            }
        ]
    if role == "code_owner":
        tables["ownership_scope"] = [
            {
                "scope_id": "scope-required-files",
                "file_glob": bundle.required_approval_files[0]
                if bundle.required_approval_files
                else "",
                "owner_id": owner_id,
                "role_id": "code_owner",
            }
        ]
    return tables


def _format_paths(paths: tuple[str, ...]) -> str:
    return ", ".join(paths) if paths else "(none)"
