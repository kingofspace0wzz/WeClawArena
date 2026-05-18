from __future__ import annotations

import json
from pathlib import Path

from clawsocialarena.attacks.runtime_overlay import materialize_runtime_variant
from clawsocialarena.generator.family_packs.marble_bargaining import (
    load_bargaining_scenario,
    materialize_bargaining_bundle,
)


def test_runtime_overlay_uses_bargaining_mode_local_recipe(tmp_path: Path) -> None:
    store = tmp_path / "store"
    base_id = "CU-A-marble_bargaining__t0"
    base_dir = store / "bargaining" / base_id
    bundle = load_bargaining_scenario(scenario_id=base_id)
    materialize_bargaining_bundle(bundle, base_dir)

    variant_dir = materialize_runtime_variant(
        store_dir=store,
        base_id=base_id,
        attack_mode="security",
        run_dir=tmp_path / "run",
        bundle_dir=f"bargaining/{base_id}",
        seed=3,
    )

    metadata = json.loads((variant_dir / "phase5_variant_metadata.json").read_text())
    scenario = json.loads((variant_dir / "scenario.json").read_text())

    assert metadata["attack"]["attack_recipe"] == "mode_local_playbook"
    assert (
        metadata["attack"]["metadata"]["playbook_id"]
        == "security_bargaining_stress_v1"
    )
    assert scenario["injected_messages"]
    assert (
        metadata["attack"]["metadata"]["tactics"][0]["tactic_id"]
        == "poisoned_market_notice"
    )


def test_runtime_overlay_keeps_general_recipe_for_non_bargaining() -> None:
    from clawsocialarena.attacks.runtime_overlay import _recipe_name_for

    assert (
        _recipe_name_for(family_id="marble_research", attack_mode="security")
        == "indirect_resource_prompt_injection"
    )
