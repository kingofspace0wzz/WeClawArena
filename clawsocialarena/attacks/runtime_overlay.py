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


AXIS_TO_RECIPE: dict[str, str] = {
    "security": "indirect_resource_prompt_injection",
    "privacy": "adaptive_exfiltration",
    "governance": "poisoned_consent_row",
    "collaboration": "adaptive_malicious_peer",
}

# Private alias kept for backwards-compat within this module.
_AXIS_TO_RECIPE = AXIS_TO_RECIPE


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

    recipe_name = AXIS_TO_RECIPE.get(attack_mode)
    if recipe_name is None or recipe_name not in registry:
        raise KeyError(
            f"no stress recipe registered for attack_mode={attack_mode!r}"
        )
    recipe = registry[recipe_name]

    base_bundle = _load_base_bundle_for_recipe(variant_dir)
    family_id = str(base_bundle.get("family_id") or "")
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

    Returns ``{recipe: None, applied: False}`` when ``attack_mode`` has no
    registered recipe; the caller can treat this as a no-op.
    """
    registry = recipe_registry or STRESS_RECIPE_REGISTRY
    recipe_name = AXIS_TO_RECIPE.get(attack_mode)
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
