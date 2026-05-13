"""Test the runtime overlay extracted into clawsocialarena.attacks.runtime_overlay."""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest


def _make_minimal_base(tmp_path: Path) -> Path:
    """Stand up a minimal tau2_telecom-shaped base bundle dir."""
    base = tmp_path / "store" / "MG-A-tau2_telecom__t0"
    base.mkdir(parents=True)
    (base / "scenario.json").write_text(json.dumps({
        "scenario_id": "test",
        "agent_graph": {"nodes": [
            {"agent_id": "leo_assistant", "role_label": "primary_account_holder", "owner_id": "leo"},
            {"agent_id": "maya_assistant", "role_label": "secondary_line_owner", "owner_id": "maya"},
        ]},
        "agents": [
            {"agent_id": "leo_assistant", "user_id": "leo"},
            {"agent_id": "maya_assistant", "user_id": "maya"},
        ],
        "opening_message": {"from": "system", "to": "leo_assistant", "content": "test"},
    }))
    (base / "scenario.gt.json").write_text(json.dumps({
        "governance_manifest": {
            "governed_actions": {"a1": {"agent_id": "leo_assistant"}},
            "approval_mandates": [],
        },
        "resource_manifest": {"resources": []},
        "construction_manifest": {"family_id": "tau2_telecom"},
    }))
    (base / "family_pack_context.json").write_text("{}")
    return base


def test_materialize_runtime_variant_no_attacker_copies_base(tmp_path: Path) -> None:
    """no_attacker mode produces a clean copy of the base, no overlay artifacts."""
    from clawsocialarena.attacks.runtime_overlay import materialize_runtime_variant

    base = _make_minimal_base(tmp_path)
    store_dir = tmp_path / "store"
    run_dir = tmp_path / "pilot" / "run1"
    variant_dir = materialize_runtime_variant(
        store_dir=store_dir,
        base_id="MG-A-tau2_telecom__t0",
        attack_mode="no_attacker",
        run_dir=run_dir,
    )
    assert variant_dir.is_dir()
    assert (variant_dir / "scenario.json").is_file()
    assert (variant_dir / "scenario.gt.json").is_file()
    # No overlay artifacts on a baseline row.
    scenario = json.loads((variant_dir / "scenario.json").read_text())
    assert "test" in scenario["opening_message"]["content"]


def test_materialize_runtime_variant_security_applies_overlay(tmp_path: Path) -> None:
    """security mode runs the indirect_resource_prompt_injection recipe."""
    from clawsocialarena.attacks.runtime_overlay import materialize_runtime_variant

    base = _make_minimal_base(tmp_path)
    variant_dir = materialize_runtime_variant(
        store_dir=tmp_path / "store",
        base_id="MG-A-tau2_telecom__t0",
        attack_mode="security",
        run_dir=tmp_path / "pilot" / "run1",
    )
    # The security recipe writes a resource file under variant_dir/resources/.
    # The exact path depends on the recipe's per-family routing, but at least
    # one file write or db insert should be present.
    resources = variant_dir / "resources"
    assert resources.is_dir(), "security overlay should materialize resources/"


def test_materialize_runtime_variant_missing_base_raises(tmp_path: Path) -> None:
    """Looking up a base that does not exist in the store raises clearly."""
    from clawsocialarena.attacks.runtime_overlay import materialize_runtime_variant

    with pytest.raises(FileNotFoundError, match="MG-A-tau2_telecom__t99"):
        materialize_runtime_variant(
            store_dir=tmp_path / "store",
            base_id="MG-A-tau2_telecom__t99",
            attack_mode="no_attacker",
            run_dir=tmp_path / "pilot" / "run1",
        )


def test_apply_recipe_to_variant_dir_security_applies(tmp_path: Path) -> None:
    """apply_recipe_to_variant_dir returns applied=True and expected keys for security axis."""
    from clawsocialarena.attacks.runtime_overlay import (
        apply_recipe_to_variant_dir,
        _load_base_bundle_for_recipe,
        materialize_runtime_variant,
    )

    base = _make_minimal_base(tmp_path)
    # Materialize a no_attacker variant dir so the files exist.
    variant_dir = materialize_runtime_variant(
        store_dir=tmp_path / "store",
        base_id="MG-A-tau2_telecom__t0",
        attack_mode="no_attacker",
        run_dir=tmp_path / "pilot" / "run1",
    )
    base_bundle = _load_base_bundle_for_recipe(variant_dir)
    outcome = apply_recipe_to_variant_dir(
        variant_dir=variant_dir,
        attack_mode="security",
        base_bundle=base_bundle,
        family_id="tau2_telecom",
        seed=42,
    )
    assert outcome["applied"] is True
    assert outcome["recipe"] == "indirect_resource_prompt_injection"
    assert "_artifacts" in outcome


def test_apply_recipe_to_variant_dir_unknown_axis_returns_noop(tmp_path: Path) -> None:
    """apply_recipe_to_variant_dir returns the no-op sentinel for unknown attack modes."""
    from clawsocialarena.attacks.runtime_overlay import apply_recipe_to_variant_dir

    base = _make_minimal_base(tmp_path)
    variant_dir = tmp_path / "store" / "MG-A-tau2_telecom__t0"

    files_before = set(variant_dir.rglob("*"))
    outcome = apply_recipe_to_variant_dir(
        variant_dir=variant_dir,
        attack_mode="no_attacker",
        base_bundle={},
        family_id="tau2_telecom",
        seed=42,
    )
    files_after = set(variant_dir.rglob("*"))

    assert outcome == {"recipe": None, "applied": False}
    assert files_before == files_after, "no files should be written for a no-op axis"


def test_load_base_bundle_promotes_family_id_from_construction_manifest(
    tmp_path: Path,
) -> None:
    """_load_base_bundle_for_recipe surfaces family_id from construction_manifest."""
    from clawsocialarena.attacks.runtime_overlay import _load_base_bundle_for_recipe

    # Build a variant dir whose scenario.gt.json nests family_id under
    # construction_manifest only (no top-level family_id).
    variant_dir = tmp_path / "variant"
    variant_dir.mkdir()
    (variant_dir / "scenario.json").write_text(json.dumps({
        "scenario_id": "test",
    }))
    (variant_dir / "scenario.gt.json").write_text(json.dumps({
        "construction_manifest": {"family_id": "tau2_telecom"},
    }))

    bundle = _load_base_bundle_for_recipe(variant_dir)
    assert bundle["family_id"] == "tau2_telecom"


def test_materialize_runtime_variant_default_seed_is_deterministic(
    tmp_path: Path,
) -> None:
    """Calling materialize_runtime_variant twice with no explicit seed produces identical scenario.json."""
    from clawsocialarena.attacks.runtime_overlay import materialize_runtime_variant

    _make_minimal_base(tmp_path)
    store_dir = tmp_path / "store"

    variant_dir1 = materialize_runtime_variant(
        store_dir=store_dir,
        base_id="MG-A-tau2_telecom__t0",
        attack_mode="security",
        run_dir=tmp_path / "run1",
    )
    variant_dir2 = materialize_runtime_variant(
        store_dir=store_dir,
        base_id="MG-A-tau2_telecom__t0",
        attack_mode="security",
        run_dir=tmp_path / "run2",
    )

    content1 = (variant_dir1 / "scenario.json").read_bytes()
    content2 = (variant_dir2 / "scenario.json").read_bytes()
    assert content1 == content2, (
        "Default seed must be deterministic: two calls with the same "
        "(base_id, attack_mode) must produce identical scenario.json bytes."
    )
