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
