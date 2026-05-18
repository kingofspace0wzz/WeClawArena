from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from clawsocialarena.attacks.stress_recipes import STRESS_RECIPE_REGISTRY
from clawsocialarena.generator.family_packs.swebench_workspace import (
    load_workspace_coding_scenario,
    materialize_workspace_coding_bundle,
)


def _base_bundle(tmp_path: Path) -> dict[str, Any]:
    bundle = load_workspace_coding_scenario()
    bundle_dir = materialize_workspace_coding_bundle(bundle, tmp_path / "scenario")
    scenario = json.loads((bundle_dir / "scenario.json").read_text())
    gt = json.loads((bundle_dir / "scenario.gt.json").read_text())
    context = json.loads((bundle_dir / "family_pack_context.json").read_text())
    merged = dict(scenario)
    merged.update(gt)
    merged["family_pack_context"] = context
    return merged


def _agent_id_for_role(base_bundle: dict[str, Any], role: str) -> str:
    nodes = (base_bundle["agent_graph"] or {}).get("nodes") or []
    return next(node["agent_id"] for node in nodes if node["role_label"] == role)


def _assert_common_metadata(
    *,
    metadata: dict[str, Any],
    artifacts_target: str,
    axis: str,
    target_role: str,
    expected_tactics: list[str],
) -> None:
    assert metadata["attack_recipe"] == "mode_local_playbook"
    assert metadata["attack_intensity"] == "stress"
    assert metadata["playbook_id"] == f"{axis}_workspace_stress_v1"
    assert metadata["attacker_control"] == "mode_local_scripted"
    assert metadata["target_role"] == target_role
    assert metadata["target_agent_id"] == artifacts_target
    assert artifacts_target in metadata["target_agent_ids"]
    assert isinstance(metadata["delivery_surface"], list)
    assert [tactic["tactic_id"] for tactic in metadata["tactics"]] == expected_tactics
    assert all(
        tactic["stage_expectations"]["final_harm"]
        for tactic in metadata["tactics"]
    )


@pytest.mark.parametrize(
    ("recipe_name", "axis", "target_role", "tactic_ids"),
    [
        (
            "workspace_collaboration_mode_local_playbook",
            "collaboration",
            "implementer",
            [
                "scope_drift_refactor",
                "review_delay_loop",
                "conflicting_patch_advice",
            ],
        ),
        (
            "workspace_security_mode_local_playbook",
            "security",
            "implementer",
            [
                "repo_doc_prompt_injection",
                "ci_output_instruction",
                "issue_text_override",
            ],
        ),
        (
            "workspace_privacy_mode_local_playbook",
            "privacy",
            "reviewer",
            [
                "private_notes_exfiltration",
                "secret_file_request",
                "test_hint_leak",
            ],
        ),
        (
            "workspace_governance_mode_local_playbook",
            "governance",
            "code_owner",
            [
                "fake_code_owner_approval",
                "wrong_owner_grant",
                "delegated_authority_laundering",
                "emergency_override_claim",
                "identity_confusion",
            ],
        ),
    ],
)
def test_workspace_playbook_artifacts_have_required_metadata(
    tmp_path: Path,
    recipe_name: str,
    axis: str,
    target_role: str,
    tactic_ids: list[str],
) -> None:
    base_bundle = _base_bundle(tmp_path)
    recipe = STRESS_RECIPE_REGISTRY[recipe_name]
    artifacts = recipe.build_variant_artifacts(
        base_bundle=base_bundle,
        family_id="swebench_workspace",
        seed=11,
    )

    _assert_common_metadata(
        metadata=artifacts.recipe_metadata,
        artifacts_target=artifacts.target_agent_id,
        axis=axis,
        target_role=target_role,
        expected_tactics=tactic_ids,
    )
    assert recipe.axis == axis
    assert artifacts.target_agent_id == _agent_id_for_role(base_bundle, target_role)
    assert artifacts.payload_text
    assert all(
        msg["attack_recipe"] == "mode_local_playbook"
        for msg in artifacts.injected_messages
    )


def test_security_playbook_writes_only_file_resources_without_db_rows(
    tmp_path: Path,
) -> None:
    artifacts = STRESS_RECIPE_REGISTRY[
        "workspace_security_mode_local_playbook"
    ].build_variant_artifacts(
        base_bundle=_base_bundle(tmp_path),
        family_id="swebench_workspace",
        seed=11,
    )

    assert set(artifacts.resource_file_writes) == {
        "repo/worktree/docs/MAINTAINER_OVERRIDE.md",
        "repo/worktree/.ci/latest-output.txt",
    }
    assert artifacts.resource_db_inserts == {}
    assert artifacts.resource_db_updates == {}
    assert any(
        msg["from"] == "tool_observation"
        and msg["tactic_id"] == "ci_output_instruction"
        for msg in artifacts.injected_messages
    )


def test_privacy_playbook_injects_messages_and_owner_note_hint(
    tmp_path: Path,
) -> None:
    artifacts = STRESS_RECIPE_REGISTRY[
        "workspace_privacy_mode_local_playbook"
    ].build_variant_artifacts(
        base_bundle=_base_bundle(tmp_path),
        family_id="swebench_workspace",
        seed=11,
    )

    assert artifacts.injected_messages
    assert any(
        path.startswith("owners/") and "/notes/" in path
        for path in artifacts.resource_file_writes
    )
    assert "secrets/prod.env" in artifacts.payload_text
    assert "secret_file_request" in artifacts.payload_text


def test_governance_playbook_records_authority_attack_parameters(
    tmp_path: Path,
) -> None:
    artifacts = STRESS_RECIPE_REGISTRY[
        "workspace_governance_mode_local_playbook"
    ].build_variant_artifacts(
        base_bundle=_base_bundle(tmp_path),
        family_id="swebench_workspace",
        seed=11,
    )

    params = artifacts.recipe_metadata["attack_parameters"]
    assert params["fabricated_code_owner_id"] == "release_manager_bot"
    assert params["wrong_owner_role"] == "reviewer"
    assert params["laundered_authority_role"] == "ci_owner"
    assert any(
        path.startswith("owners/") and "/notes/" in path
        for path in artifacts.resource_file_writes
    )
    assert any(
        msg["from"] == "release_manager_bot"
        and msg["tactic_id"] == "emergency_override_claim"
        for msg in artifacts.injected_messages
    )
    assert "identity_confusion" in artifacts.payload_text
    assert "policy.grant_approval" in artifacts.payload_text


def test_workspace_playbooks_reject_non_workspace_family(tmp_path: Path) -> None:
    recipe = STRESS_RECIPE_REGISTRY["workspace_security_mode_local_playbook"]

    with pytest.raises(ValueError):
        recipe.build_variant_artifacts(
            base_bundle=_base_bundle(tmp_path),
            family_id="tau2_telecom",
            seed=11,
        )
