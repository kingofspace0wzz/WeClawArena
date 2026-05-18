from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from clawsocialarena.eval.workspace_asr_judge import load_workspace_context_for_row
from clawsocialarena.generator.family_packs.swebench_workspace import (
    load_workspace_coding_scenario,
    materialize_workspace_coding_bundle,
)


def test_v2_judge_context_includes_evidence_chain_resources(tmp_path: Path) -> None:
    bundle = load_workspace_coding_scenario(workspace_substrate_version="v2")
    bundle_dir = materialize_workspace_coding_bundle(bundle, tmp_path / "scenario")
    evidence_chain = {
        "patch_applies": True,
        "required_files_changed": True,
        "evidence_chain_complete": True,
    }
    maya_db = bundle_dir / "resources" / "owners" / "maya" / "db" / "personal.sqlite"
    with sqlite3.connect(maya_db) as conn:
        conn.execute(
            "UPDATE workspace_runs "
            "SET evidence_chain = ?, current_patch_hash = ? "
            "WHERE instance_id = ?",
            (json.dumps(evidence_chain), "sha256:current-patch", bundle.instance_id),
        )

    row = {
        "variant_id": f"{bundle.scenario.scenario_id}__security",
        "base_scenario_id": bundle.scenario.scenario_id,
        "attack_mode": "security",
        "extra": {"bundle_dir": str(bundle_dir)},
    }

    context = load_workspace_context_for_row(row=row)

    assert context["workspace_substrate_version"] == "v2"
    assert context["owner_evidence_files"]["maya/notes/repro.md"].startswith(
        "# Reproduction Notes"
    )
    assert "nolan/review/checklist.md" in context["owner_evidence_files"]
    assert "opal/ownership/approval_policy.md" in context["owner_evidence_files"]
    assert "opal/ownership/stale_approval_notes.md" in context["owner_evidence_files"]
    assert "priya/ci/regression_result.md" in context["owner_evidence_files"]
    assert "priya/ci/flaky_notes.md" in context["owner_evidence_files"]
    assert all(
        len(content) <= 1203
        for content in context["owner_evidence_files"].values()
    )
    assert context["evidence_chain"] == evidence_chain
    assert context["current_patch_hash"] == "sha256:current-patch"
