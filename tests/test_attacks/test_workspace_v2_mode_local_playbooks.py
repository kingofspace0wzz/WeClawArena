from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawsocialarena.attacks.stress_recipes import STRESS_RECIPE_REGISTRY
from clawsocialarena.generator.family_packs.swebench_workspace import (
    load_workspace_coding_scenario,
    materialize_workspace_coding_bundle,
)


def _base_bundle(tmp_path: Path) -> dict:
    bundle = load_workspace_coding_scenario(workspace_substrate_version="v2")
    bundle_dir = materialize_workspace_coding_bundle(bundle, tmp_path / "scenario")
    scenario = json.loads((bundle_dir / "scenario.json").read_text())
    gt = json.loads((bundle_dir / "scenario.gt.json").read_text())
    context = json.loads((bundle_dir / "family_pack_context.json").read_text())
    merged = dict(scenario)
    merged.update(gt)
    merged["family_pack_context"] = context
    return merged


@pytest.mark.parametrize(
    ("recipe_name", "axis", "required_tactics"),
    [
        (
            "workspace_security_mode_local_playbook_v2",
            "security",
            [
                "poisoned_ci_false_pass",
                "forbidden_file_fix_instruction",
                "unsafe_submit_instruction",
            ],
        ),
        (
            "workspace_governance_mode_local_playbook_v2",
            "governance",
            [
                "stale_patch_approval",
                "delegated_authority_laundering",
                "owner_agent_identity_confusion",
            ],
        ),
        (
            "workspace_collaboration_mode_local_playbook_v2",
            "collaboration",
            [
                "wrong_repro_evidence",
                "poisoned_review_checklist",
                "ci_review_deadlock",
            ],
        ),
    ],
)
def test_v2_playbooks_target_workflow_evidence(
    tmp_path: Path,
    recipe_name: str,
    axis: str,
    required_tactics: list[str],
) -> None:
    artifacts = STRESS_RECIPE_REGISTRY[recipe_name].build_variant_artifacts(
        base_bundle=_base_bundle(tmp_path),
        family_id="swebench_workspace",
        seed=19,
    )

    metadata = artifacts.recipe_metadata
    assert metadata["attack_recipe"] == "workspace_mode_local_playbook_v2"
    assert metadata["attack_intensity"] == "stress"
    assert metadata["playbook_id"] == f"{axis}_workspace_stress_v2"
    assert metadata["workspace_substrate_version"] == "v2"
    assert [t["tactic_id"] for t in metadata["tactics"]] == required_tactics
    assert all(t["stage_expectations"]["final_harm"] for t in metadata["tactics"])
    assert artifacts.payload_text.strip()
    assert artifacts.resource_db_updates == {}
