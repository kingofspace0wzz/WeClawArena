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
produce identical output bytes. Seed defaults to a SHA-256-derived
integer of ``(base_id, attack_mode)``; pass an explicit ``seed`` if
you need to vary the recipe output for a given base+axis pair.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

from clawsocialarena.attacks.stress_recipes import (
    STRESS_RECIPE_REGISTRY,
    StressRecipe,
    StressVariantArtifacts,
)
from clawsocialarena.generator.phase5_store_layout import resolve_store_base_dir


AXIS_TO_RECIPE: dict[str, str] = {
    "security": "indirect_resource_prompt_injection",
    "privacy": "adaptive_exfiltration",
    "governance": "poisoned_consent_row",
    "collaboration": "adaptive_malicious_peer",
}

FAMILY_AXIS_TO_RECIPE: dict[tuple[str, str], str] = {
    (
        "marble_bargaining",
        "collaboration",
    ): "bargaining_collaboration_mode_local_playbook",
    ("marble_bargaining", "security"): "bargaining_security_mode_local_playbook",
    ("marble_bargaining", "privacy"): "bargaining_privacy_mode_local_playbook",
    ("marble_bargaining", "governance"): "bargaining_governance_mode_local_playbook",
    (
        "marble_bidding",
        "collaboration",
    ): "bidding_collaboration_mode_local_playbook",
    ("marble_bidding", "security"): "bidding_security_mode_local_playbook",
    ("marble_bidding", "privacy"): "bidding_privacy_mode_local_playbook",
    ("marble_bidding", "governance"): "bidding_governance_mode_local_playbook",
    (
        "swebench_workspace",
        "collaboration",
    ): "workspace_collaboration_mode_local_playbook",
    ("swebench_workspace", "security"): "workspace_security_mode_local_playbook",
    ("swebench_workspace", "privacy"): "workspace_privacy_mode_local_playbook",
    ("swebench_workspace", "governance"): "workspace_governance_mode_local_playbook",
    ("travel", "security"): "travel_security_mode_local_playbook",
    ("travel", "privacy"): "travel_privacy_mode_local_playbook",
    ("travel", "governance"): "travel_governance_mode_local_playbook",
    ("travel", "collaboration"): "travel_collaboration_mode_local_playbook",
}

# Private alias kept for backwards-compat within this module.
_AXIS_TO_RECIPE = AXIS_TO_RECIPE


def _workspace_substrate_version(base_bundle: dict[str, Any]) -> str:
    context = base_bundle.get("family_pack_context")
    if isinstance(context, dict) and context.get("workspace_substrate_version"):
        return str(context["workspace_substrate_version"])
    metadata = base_bundle.get("phase5_metadata")
    if isinstance(metadata, dict) and metadata.get("workspace_substrate_version"):
        return str(metadata["workspace_substrate_version"])
    return "v1"


def _recipe_name_for(
    *,
    family_id: str,
    attack_mode: str,
    base_bundle: dict[str, Any] | None = None,
) -> str | None:
    if (
        family_id == "swebench_workspace"
        and base_bundle is not None
        and _workspace_substrate_version(base_bundle) == "v2"
        and attack_mode in {"security", "governance", "privacy", "collaboration"}
    ):
        return f"workspace_{attack_mode}_resource_bound_playbook"
    return FAMILY_AXIS_TO_RECIPE.get((family_id, attack_mode)) or AXIS_TO_RECIPE.get(
        attack_mode
    )


def materialize_runtime_variant(
    *,
    store_dir: Path,
    base_id: str,
    attack_mode: str,
    run_dir: Path,
    bundle_dir: str | Path | None = None,
    recipe_registry: dict[str, StressRecipe] | None = None,
    seed: int | None = None,
) -> Path:
    """Copy a base bundle from the v2 store and apply the stress overlay.

    Raises:
        FileNotFoundError: when the base cannot be found in either the
            manifest path, ``store_dir/<domain>/<base_id>/``, or the legacy
            ``store_dir/<base_id>/`` flat path.
        KeyError: when ``attack_mode`` is non-baseline but its recipe
            is missing from ``recipe_registry`` (default
            ``STRESS_RECIPE_REGISTRY``).
    """
    registry = recipe_registry or STRESS_RECIPE_REGISTRY
    src_dir = resolve_store_base_dir(
        store_dir=store_dir,
        base_id=base_id,
        bundle_dir=bundle_dir,
    )

    variant_id = f"{base_id}__{attack_mode}"
    variant_dir = run_dir / "variants" / variant_id
    variant_dir.parent.mkdir(parents=True, exist_ok=True)
    if variant_dir.exists():
        shutil.rmtree(variant_dir)
    shutil.copytree(src_dir, variant_dir)

    if attack_mode == "no_attacker":
        return variant_dir

    base_bundle = _load_base_bundle_for_recipe(variant_dir)
    family_id = str(base_bundle.get("family_id") or "")
    recipe_name = _recipe_name_for(
        family_id=family_id,
        attack_mode=attack_mode,
        base_bundle=base_bundle,
    )
    if recipe_name is None or recipe_name not in registry:
        raise KeyError(
            f"no stress recipe registered for attack_mode={attack_mode!r}"
        )
    recipe = registry[recipe_name]

    if seed is not None:
        deterministic_seed = seed
    else:
        digest = hashlib.sha256(
            (base_id + "::" + attack_mode).encode()
        ).hexdigest()
        deterministic_seed = int(digest[:8], 16) % 1000
    artifacts = recipe.build_variant_artifacts(
        base_bundle=base_bundle, family_id=family_id, seed=deterministic_seed
    )
    _apply_artifacts(variant_dir=variant_dir, artifacts=artifacts)
    _write_runtime_variant_metadata(
        variant_dir=variant_dir,
        base_id=base_id,
        attack_mode=attack_mode,
        family_id=family_id,
        recipe_name=recipe_name,
        artifacts=artifacts,
    )
    return variant_dir


def _load_base_bundle_for_recipe(variant_dir: Path) -> dict[str, Any]:
    """Merge scenario.json + scenario.gt.json so the recipe can read either.

    Also promotes ``construction_manifest.family_id`` to the top-level
    ``family_id`` key so callers can use ``bundle.get("family_id")`` without
    inspecting the nested structure.
    """
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
    context_path = variant_dir / "family_pack_context.json"
    if context_path.is_file():
        try:
            context = json.loads(context_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            context = None
        if isinstance(context, dict):
            merged["family_pack_context"] = context
    return merged


def _write_runtime_variant_metadata(
    *,
    variant_dir: Path,
    base_id: str,
    attack_mode: str,
    family_id: str,
    recipe_name: str,
    artifacts: StressVariantArtifacts,
) -> None:
    metadata = {
        "phase5_version": 1,
        "variant_id": f"{base_id}__{attack_mode}",
        "base_scenario_id": base_id,
        "family_id": family_id,
        "attack": {
            "attack_mode": attack_mode,
            "attack_recipe": artifacts.recipe_metadata.get(
                "attack_recipe", recipe_name
            ),
            "attack_intensity": artifacts.recipe_metadata.get(
                "attack_intensity", "stress"
            ),
            "delivery_surface": artifacts.recipe_metadata.get(
                "delivery_surface", "message"
            ),
            "attacker_control": artifacts.recipe_metadata.get(
                "attacker_control", "scripted_multi_turn"
            ),
            "target_agent_id": artifacts.target_agent_id,
            "payload_text": artifacts.payload_text,
            "metadata": dict(artifacts.recipe_metadata),
            "requires_runtime_peer": artifacts.requires_runtime_peer,
            "attacker_peer_id": artifacts.attacker_peer_id,
            "attacker_peer_prompt": artifacts.attacker_peer_prompt,
            "attacker_peer_max_turns": artifacts.attacker_peer_max_turns,
        },
    }
    (variant_dir / "phase5_variant_metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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

    Returns ``{recipe: None, applied: False}`` when ``attack_mode`` has no
    registered recipe; the caller can treat this as a no-op.
    """
    registry = recipe_registry or STRESS_RECIPE_REGISTRY
    recipe_name = _recipe_name_for(
        family_id=family_id,
        attack_mode=attack_mode,
        base_bundle=base_bundle,
    )
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

    Returns (file_writes, db_inserts, db_updates) report lists.
    """
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


def _seed_variant_resource_dirs(variant_dir: Path) -> None:
    """Ensure the variant has its own ``resources/`` and
    ``resources_initial/`` trees, seeded from the base bundle.

    Two reasons we need a per-variant copy of both trees:

    1. The live executor's ``_restore_resources_from_snapshot``
       runs a destructive ``rmtree(resources) + copytree(resources_initial)``
       at the start of every scenario. Any stress overlay that lives
       ONLY in ``resources/`` gets wiped. So we must also stamp the
       overlay into ``resources_initial/`` so the post-restore state
       still carries the recipe mutations.

    2. The base bundle's resources/ and resources_initial/ are shared
       across all five variants (no_attacker + 4 axes). Mutating them
       would change the baseline. We materialize a per-variant copy
       so each recipe's overlay is isolated.
    """
    resources_root = variant_dir / "resources"
    resources_initial_root = variant_dir / "resources_initial"

    if resources_root.is_dir():
        resources_initial_root.mkdir(parents=True, exist_ok=True)
        for src in resources_root.rglob("*"):
            if src.is_file():
                rel = src.relative_to(resources_root)
                dest = resources_initial_root / rel
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)

    for which in ("resources", "resources_initial"):
        target_root = variant_dir / which
        target_root.mkdir(parents=True, exist_ok=True)
        base_dir_path = variant_dir.parent.parent / which
        if base_dir_path.is_dir():
            for src in base_dir_path.rglob("*"):
                if src.is_file():
                    rel = src.relative_to(base_dir_path)
                    dest = target_root / rel
                    if not dest.exists():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dest)


def _apply_resource_file_writes(
    *,
    variant_dir: Path,
    writes: dict[str, str | bytes],
) -> list[str]:
    """Write resource-relative files into BOTH
    ``variant_dir/resources/`` and ``variant_dir/resources_initial/``.

    Mirroring into both trees is required because the live executor
    rmtree's ``resources/`` and copytree's it back from
    ``resources_initial/`` on every scenario start. See
    :func:`_seed_variant_resource_dirs` for the full rationale.

    Returns the list of relative paths actually written.
    """
    written: list[str] = []
    if not writes:
        return written
    _seed_variant_resource_dirs(variant_dir)
    for rel_path, content in writes.items():
        # Recipe authors mix conventions: some prefix paths with
        # ``resources/`` (e.g., ``resources/account/.../lines.json``),
        # others use a resource-root-relative path (e.g.,
        # ``users/bob/db/personal.sqlite``). Normalize by stripping a
        # leading ``resources/`` so both styles land at the same place
        # under the variant's resources/ tree.
        normalized = rel_path
        if normalized.startswith("resources/"):
            normalized = normalized[len("resources/"):]
        for which in ("resources", "resources_initial"):
            dest = variant_dir / which / normalized
            dest.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                dest.write_bytes(content)
            else:
                dest.write_text(str(content), encoding="utf-8")
        written.append(normalized)
    return written


def _ensure_db_overlay(*, variant_dir: Path, db_relpath: str) -> list[Path]:
    """Ensure the variant has its own copy of the per-user sqlite db
    under BOTH ``resources/`` and ``resources_initial/``.

    Returns both target paths so the caller can apply the same
    mutation to each (so the live executor's snapshot restore does
    not wipe the recipe overlay -- see
    :func:`_seed_variant_resource_dirs` for the rationale).

    Path normalization matches ``_apply_resource_file_writes``: a
    leading ``resources/`` is stripped so both
    ``resources/users/x/db/personal.sqlite`` and
    ``users/x/db/personal.sqlite`` land in the same place.
    """
    normalized = db_relpath
    if normalized.startswith("resources/"):
        normalized = normalized[len("resources/"):]
    _seed_variant_resource_dirs(variant_dir)
    paths: list[Path] = []
    for which in ("resources", "resources_initial"):
        base_dir_path = variant_dir.parent.parent / which
        target = variant_dir / which / normalized
        if not target.exists():
            src = base_dir_path / normalized
            target.parent.mkdir(parents=True, exist_ok=True)
            if src.is_file():
                shutil.copy2(src, target)
            else:
                # The base db is missing; create an empty sqlite file so
                # the connection succeeds. The handler will materialize
                # schema on first read.
                sqlite3.connect(str(target)).close()
        paths.append(target)
    return paths


def _apply_resource_db_inserts(
    *,
    variant_dir: Path,
    inserts: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[str]:
    """Insert rows into per-user sqlite tables under variant_dir."""
    if not inserts:
        return []
    applied: list[str] = []
    for (db_relpath, table), rows in inserts.items():
        if not rows:
            continue
        db_paths = _ensure_db_overlay(
            variant_dir=variant_dir, db_relpath=db_relpath
        )
        for db_path in db_paths:
            conn = sqlite3.connect(str(db_path))
            try:
                cursor = conn.cursor()
                for row in rows:
                    cols = sorted(row.keys())
                    placeholders = ", ".join(["?"] * len(cols))
                    col_list = ", ".join(cols)
                    values: list[Any] = []
                    for col in cols:
                        val = row[col]
                        if isinstance(val, (dict, list)):
                            val = json.dumps(val, sort_keys=True)
                        values.append(val)
                    try:
                        cursor.execute(
                            f"INSERT OR REPLACE INTO {table} ({col_list}) "
                            f"VALUES ({placeholders})",
                            values,
                        )
                    except sqlite3.OperationalError as exc:
                        # Table or columns missing -- log but don't crash.
                        print(
                            f"  warn: insert into {db_relpath}::{table} "
                            f"failed ({exc}); recipe should declare a "
                            "fallback artifact",
                            file=sys.stderr,
                        )
                conn.commit()
            finally:
                conn.close()
        applied.append(f"{db_relpath}::{table}")
    return applied


def _apply_resource_db_updates(
    *,
    variant_dir: Path,
    updates: dict[tuple[str, str, str, Any], dict[str, Any]],
) -> list[str]:
    """Apply UPDATE statements to per-user sqlite tables."""
    if not updates:
        return []
    applied: list[str] = []
    for (db_relpath, table, pk_col, pk_val), col_updates in updates.items():
        if not col_updates:
            continue
        db_paths = _ensure_db_overlay(
            variant_dir=variant_dir, db_relpath=db_relpath
        )
        for db_path in db_paths:
            conn = sqlite3.connect(str(db_path))
            try:
                cursor = conn.cursor()
                set_clauses: list[str] = []
                values: list[Any] = []
                for col, val in col_updates.items():
                    if isinstance(val, (dict, list)):
                        val = json.dumps(val, sort_keys=True)
                    set_clauses.append(f"{col} = ?")
                    values.append(val)
                values.append(pk_val)
                sql = (
                    f"UPDATE {table} SET {', '.join(set_clauses)} "
                    f"WHERE {pk_col} = ?"
                )
                try:
                    cursor.execute(sql, values)
                except sqlite3.OperationalError as exc:
                    print(
                        f"  warn: update on {db_relpath}::{table} failed "
                        f"({exc}); recipe should declare a fallback artifact",
                        file=sys.stderr,
                    )
                conn.commit()
            finally:
                conn.close()
        applied.append(f"{db_relpath}::{table}({pk_col}={pk_val})")
    return applied


def _apply_scenario_mutations(
    *,
    variant_dir: Path,
    artifacts: StressVariantArtifacts,
) -> None:
    """Append the recipe's opening_message addendum + injected_messages
    to the variant's scenario.json (in place).
    """
    scenario_path = variant_dir / "scenario.json"
    if not scenario_path.is_file():
        return
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    if artifacts.opening_message_addendum:
        opening = scenario.get("opening_message") or {}
        existing = str(opening.get("content") or "")
        opening["content"] = (
            existing + "\n\n" + artifacts.opening_message_addendum
            if existing
            else artifacts.opening_message_addendum
        )
        scenario["opening_message"] = opening
    if artifacts.injected_messages:
        existing_inj = list(scenario.get("injected_messages") or [])
        existing_inj.extend(artifacts.injected_messages)
        scenario["injected_messages"] = existing_inj
    scenario_path.write_text(
        json.dumps(scenario, indent=2, sort_keys=True), encoding="utf-8"
    )
