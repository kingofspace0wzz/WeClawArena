from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from clawsocialarena.generator.family_packs.swebench_workspace import (
    load_workspace_coding_scenario,
    materialize_workspace_coding_bundle,
)


def test_v2_materializer_writes_owned_files_and_metadata(tmp_path: Path) -> None:
    bundle = load_workspace_coding_scenario(workspace_substrate_version="v2")
    bundle_dir = materialize_workspace_coding_bundle(bundle, tmp_path / "scenario")

    metadata = json.loads((bundle_dir / "phase5_metadata.json").read_text())
    context = json.loads((bundle_dir / "family_pack_context.json").read_text())

    assert metadata["workspace_substrate_version"] == "v2"
    assert context["workspace_substrate_version"] == "v2"
    assert (
        bundle_dir / "resources" / "owners" / "maya" / "notes" / "repro.md"
    ).is_file()
    assert (
        bundle_dir / "resources" / "owners" / "nolan" / "review" / "checklist.md"
    ).is_file()
    assert (
        bundle_dir
        / "resources"
        / "owners"
        / "opal"
        / "ownership"
        / "approval_policy.md"
    ).is_file()
    assert (
        bundle_dir / "resources" / "owners" / "priya" / "ci" / "regression_result.md"
    ).is_file()
    private = (
        bundle_dir / "resources" / "owners" / "maya" / "notes" / "private.md"
    ).read_text(encoding="utf-8")
    assert "Role: implementer" in private
    assert bundle.instance_id in private
    assert bundle.required_approval_files[0] in private


def test_v2_ci_owner_can_read_owned_db_facts_without_edit_access() -> None:
    bundle = load_workspace_coding_scenario(workspace_substrate_version="v2")
    ci_node = next(
        node
        for node in bundle.scenario.agent_graph.nodes
        if node.role_label == "ci_owner"
    )
    ci_agent = next(
        agent
        for agent in bundle.scenario.agents
        if agent.agent_id == ci_node.agent_id
    )

    assert "read_owned_file" in ci_agent.allowed_tools
    assert "query_owned_table" in ci_agent.allowed_tools
    assert "repo.write" not in ci_agent.allowed_tools
    assert ci_node.scope == ci_agent.allowed_tools
    assert "query_owned_table" in ci_agent.system_prompt_template
    assert "Do not call repo.write" in ci_agent.system_prompt_template


def test_v2_materializer_writes_evidence_tables(tmp_path: Path) -> None:
    bundle = load_workspace_coding_scenario(workspace_substrate_version="v2")
    bundle_dir = materialize_workspace_coding_bundle(bundle, tmp_path / "scenario")
    expected_tables = {
        "workspace_runs",
        "patch_findings",
        "review_decisions",
        "ownership_scope",
        "owner_approvals",
        "test_runs",
        "test_claims",
        "resource_facts",
    }
    legacy_columns = [
        "instance_id",
        "patch_submitted",
        "patch_applies",
        "changed_files",
        "forbidden_files",
        "target_tests",
        "regression_tests",
        "required_approvals",
        "approvals",
        "owner_constraints",
        "workflow_state",
    ]
    v2_columns = [
        "workspace_substrate_version",
        "evidence_chain",
        "current_patch_hash",
    ]

    for owner_id in ("maya", "nolan", "opal", "priya"):
        db = bundle_dir / "resources" / "owners" / owner_id / "db" / "personal.sqlite"
        with sqlite3.connect(db) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            columns = [
                row[1] for row in conn.execute("PRAGMA table_info(workspace_runs)")
            ]
            run = conn.execute(
                "SELECT workspace_substrate_version, evidence_chain "
                "FROM workspace_runs WHERE instance_id = ?",
                (bundle.instance_id,),
            ).fetchone()
            resource_fact_count = conn.execute(
                "SELECT COUNT(*) FROM resource_facts"
            ).fetchone()[0]

        assert expected_tables <= tables
        assert columns == legacy_columns + v2_columns
        assert run[0] == "v2"
        assert json.loads(run[1])["evidence_chain_complete"] is False
        assert resource_fact_count >= 4

    maya_db = bundle_dir / "resources" / "owners" / "maya" / "db" / "personal.sqlite"
    with sqlite3.connect(maya_db) as conn:
        maya_finding = conn.execute(
            "SELECT finding_id, file_path, finding, confidence FROM patch_findings"
        ).fetchone()

    assert maya_finding == (
        "finding-required-file",
        bundle.required_approval_files[0],
        "Primary candidate file from reduced fixture.",
        0.85,
    )

    opal_db = bundle_dir / "resources" / "owners" / "opal" / "db" / "personal.sqlite"
    with sqlite3.connect(opal_db) as conn:
        opal_scope = conn.execute(
            "SELECT scope_id, file_glob, owner_id, role_id FROM ownership_scope"
        ).fetchone()

    assert opal_scope == (
        "scope-required-files",
        bundle.required_approval_files[0],
        "opal",
        "code_owner",
    )

    for owner_id in ("nolan", "priya"):
        db = bundle_dir / "resources" / "owners" / owner_id / "db" / "personal.sqlite"
        with sqlite3.connect(db) as conn:
            assert (
                conn.execute("SELECT COUNT(*) FROM review_decisions").fetchone()[0] == 0
            )
            assert conn.execute("SELECT COUNT(*) FROM test_runs").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM test_claims").fetchone()[0] == 0
