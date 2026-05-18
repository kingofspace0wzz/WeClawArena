from __future__ import annotations

import json
from pathlib import Path

from clawsocialarena.attacks.runtime_overlay import materialize_runtime_variant
from clawsocialarena.generator.family_packs.swebench_workspace import (
    load_workspace_coding_scenario,
    materialize_workspace_coding_bundle,
)


def _workspace_store_bundle(
    tmp_path: Path,
    *,
    workspace_substrate_version: str = "v1",
) -> tuple[Path, str, str]:
    store = tmp_path / "store"
    base_id = "swebench_workspace_phase5_v0"
    bundle_dir = f"workspace/{base_id}"
    bundle = load_workspace_coding_scenario(
        scenario_id=base_id,
        workspace_substrate_version=workspace_substrate_version,
    )
    materialize_workspace_coding_bundle(bundle, store / bundle_dir)
    return store, base_id, bundle_dir


def test_runtime_overlay_uses_workspace_governance_playbook(
    tmp_path: Path,
) -> None:
    store, base_id, bundle_dir = _workspace_store_bundle(tmp_path)

    variant_dir = materialize_runtime_variant(
        store_dir=store,
        base_id=base_id,
        attack_mode="governance",
        run_dir=tmp_path / "run",
        bundle_dir=bundle_dir,
        seed=5,
    )

    metadata = json.loads((variant_dir / "phase5_variant_metadata.json").read_text())
    scenario = json.loads((variant_dir / "scenario.json").read_text())

    assert metadata["attack"]["attack_recipe"] == "mode_local_playbook"
    assert (
        metadata["attack"]["metadata"]["playbook_id"]
        == "governance_workspace_stress_v1"
    )
    assert metadata["attack"]["metadata"]["target_role"] == "code_owner"
    assert scenario["injected_messages"]
    assert "release_manager_bot" in metadata["attack"]["payload_text"]


def test_runtime_overlay_writes_workspace_security_files_to_both_resource_trees(
    tmp_path: Path,
) -> None:
    store, base_id, bundle_dir = _workspace_store_bundle(tmp_path)

    variant_dir = materialize_runtime_variant(
        store_dir=store,
        base_id=base_id,
        attack_mode="security",
        run_dir=tmp_path / "run",
        bundle_dir=bundle_dir,
        seed=5,
    )

    for root_name in ("resources", "resources_initial"):
        root = variant_dir / root_name
        assert (root / "repo" / "metadata.json").is_file()
        assert (
            root / "repo" / "worktree" / "astropy" / "modeling" / "separable.py"
        ).is_file()
        assert (root / "owners" / "maya" / "db" / "personal.sqlite").is_file()
        assert (
            root / "repo" / "worktree" / "docs" / "MAINTAINER_OVERRIDE.md"
        ).is_file()
        assert (
            root / "repo" / "worktree" / ".ci" / "latest-output.txt"
        ).is_file()


def test_runtime_overlay_keeps_generic_security_recipe_for_tau2_telecom() -> None:
    from clawsocialarena.attacks.runtime_overlay import _recipe_name_for

    assert (
        _recipe_name_for(family_id="tau2_telecom", attack_mode="security")
        == "indirect_resource_prompt_injection"
    )


def test_runtime_overlay_routes_workspace_v2_axes_to_resource_bound_playbooks(
    tmp_path: Path,
) -> None:
    for attack_mode in ("security", "governance", "privacy", "collaboration"):
        store, base_id, bundle_dir = _workspace_store_bundle(
            tmp_path / attack_mode,
            workspace_substrate_version="v2",
        )

        variant_dir = materialize_runtime_variant(
            store_dir=store,
            base_id=base_id,
            attack_mode=attack_mode,
            run_dir=tmp_path / "run" / attack_mode,
            bundle_dir=bundle_dir,
            seed=5,
        )

        metadata = json.loads(
            (variant_dir / "phase5_variant_metadata.json").read_text()
        )
        assert (
            metadata["attack"]["attack_recipe"]
            == "workspace_resource_bound_playbook"
        )
        assert (
            metadata["attack"]["metadata"]["playbook_id"]
            == f"{attack_mode}_workspace_resource_bound_v1"
        )
        assert metadata["attack"]["metadata"]["target_resources"]
        assert metadata["attack"]["metadata"]["resource_bound"] is True
