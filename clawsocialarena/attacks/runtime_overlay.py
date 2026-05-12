"""Callable runtime overlay: materialize a per-run variant dir from
the v2 store + apply the stress-recipe overlay if applicable.

This module is the run-time counterpart to
``scripts/regenerate_phase5_stress_variants.py`` (which now wraps
this function). The CLI script keeps the same logic; the live
executor calls the function directly.

Layout the function produces:
    run_dir/
      variants/
        <base_id>__<attack_mode>/
          scenario.json     (base + stress overlay)
          scenario.gt.json
          personas/         (inherited)
          mcp/              (inherited)
          governance/       (inherited)
          resources_initial/(inherited + overlay)
          resources/        (inherited + overlay; mutated by handlers at run time)

The function is pure with respect to its inputs: identical inputs
produce identical output bytes (recipe determinism via the seed).
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from clawsocialarena.attacks.stress_recipes import (
    STRESS_RECIPE_REGISTRY,
    StressRecipe,
    StressVariantArtifacts,
)


_AXIS_TO_RECIPE: dict[str, str] = {
    "security": "indirect_resource_prompt_injection",
    "privacy": "adaptive_exfiltration",
    "governance": "poisoned_consent_row",
    "collaboration": "adaptive_malicious_peer",
}


def materialize_runtime_variant(
    *,
    store_dir: Path,
    base_id: str,
    attack_mode: str,
    run_dir: Path,
    recipe_registry: dict[str, StressRecipe] | None = None,
    seed: int | None = None,
) -> Path:
    """Copy a base bundle from the v2 store and apply the stress overlay.

    Raises:
        FileNotFoundError: when ``store_dir/<base_id>/`` is not a dir.
        KeyError: when ``attack_mode`` is non-baseline but its recipe
            is missing from ``recipe_registry`` (default
            ``STRESS_RECIPE_REGISTRY``).
    """
    registry = recipe_registry or STRESS_RECIPE_REGISTRY
    src_dir = store_dir / base_id
    if not src_dir.is_dir():
        raise FileNotFoundError(f"base bundle missing in store: {src_dir}")

    variant_id = f"{base_id}__{attack_mode}"
    variant_dir = run_dir / "variants" / variant_id
    variant_dir.parent.mkdir(parents=True, exist_ok=True)
    if variant_dir.exists():
        shutil.rmtree(variant_dir)
    shutil.copytree(src_dir, variant_dir)

    if attack_mode == "no_attacker":
        return variant_dir

    recipe_name = _AXIS_TO_RECIPE.get(attack_mode)
    if recipe_name is None or recipe_name not in registry:
        raise KeyError(
            f"no stress recipe registered for attack_mode={attack_mode!r}"
        )
    recipe = registry[recipe_name]

    base_bundle = _load_base_bundle_for_recipe(variant_dir)
    family_id = str(base_bundle.get("family_id") or "")
    deterministic_seed = (
        seed
        if seed is not None
        else abs(hash((base_id, attack_mode))) % 1000
    )
    artifacts = recipe.build_variant_artifacts(
        base_bundle=base_bundle, family_id=family_id, seed=deterministic_seed
    )
    _apply_artifacts(variant_dir=variant_dir, artifacts=artifacts)
    return variant_dir


def _load_base_bundle_for_recipe(variant_dir: Path) -> dict[str, Any]:
    """Merge scenario.json + scenario.gt.json so the recipe can read either.

    Also promotes ``construction_manifest.family_id`` to the top-level
    ``family_id`` key so callers can use ``bundle.get("family_id")`` without
    inspecting the nested structure.
    """
    import json

    scenario = json.loads((variant_dir / "scenario.json").read_text(encoding="utf-8"))
    gt = json.loads((variant_dir / "scenario.gt.json").read_text(encoding="utf-8"))
    merged = dict(scenario)
    for k, v in gt.items():
        if k not in merged:
            merged[k] = v
    if "family_id" not in merged:
        cm = merged.get("construction_manifest") or {}
        if isinstance(cm, dict) and cm.get("family_id"):
            merged["family_id"] = cm["family_id"]
    return merged


def apply_recipe_to_variant_dir(
    *,
    variant_dir: Path,
    attack_mode: str,
    base_bundle: dict[str, Any],
    family_id: str,
    seed: int,
    recipe_registry: dict[str, StressRecipe] | None = None,
) -> dict[str, Any]:
    """Resolve the stress recipe for ``attack_mode``, build its artifacts, and
    apply them to an existing ``variant_dir`` in place.

    Returns a report dict with ``recipe``, ``applied``, ``file_writes``,
    ``db_inserts``, ``db_updates``, and ``requires_runtime_peer`` so the
    CLI wrapper can include these in its summary without duplicating the
    recipe-dispatch logic.

    Raises:
        KeyError: when ``attack_mode`` has no registered recipe.
    """
    registry = recipe_registry or STRESS_RECIPE_REGISTRY
    recipe_name = _AXIS_TO_RECIPE.get(attack_mode)
    if not recipe_name or recipe_name not in registry:
        return {"recipe": None, "applied": False}
    recipe = registry[recipe_name]
    artifacts = recipe.build_variant_artifacts(
        base_bundle=base_bundle, family_id=family_id, seed=seed
    )
    file_writes, db_inserts, db_updates = _apply_artifacts(
        variant_dir=variant_dir, artifacts=artifacts
    )
    return {
        "recipe": recipe_name,
        "applied": True,
        "file_writes": file_writes,
        "db_inserts": db_inserts,
        "db_updates": db_updates,
        "requires_runtime_peer": artifacts.requires_runtime_peer,
        "_artifacts": artifacts,
    }


def _apply_artifacts(
    *,
    variant_dir: Path,
    artifacts: StressVariantArtifacts,
) -> tuple[list[str], list[str], list[str]]:
    """Apply file writes, db inserts/updates, scenario mutations to variant_dir.

    Delegates to the same helpers used by the one-shot regenerate script;
    we import them lazily to keep the dependency graph clean.

    Returns (file_writes, db_inserts, db_updates) report lists.
    """
    from scripts.regenerate_phase5_stress_variants import (
        _apply_resource_db_inserts,
        _apply_resource_db_updates,
        _apply_resource_file_writes,
        _apply_scenario_mutations,
    )

    file_writes = _apply_resource_file_writes(
        variant_dir=variant_dir, writes=artifacts.resource_file_writes
    )
    db_inserts = _apply_resource_db_inserts(
        variant_dir=variant_dir, inserts=artifacts.resource_db_inserts
    )
    db_updates = _apply_resource_db_updates(
        variant_dir=variant_dir, updates=artifacts.resource_db_updates
    )
    _apply_scenario_mutations(variant_dir=variant_dir, artifacts=artifacts)
    return file_writes, db_inserts, db_updates
