"""Regenerate Phase-5 attack variants using STRESS_RECIPE_REGISTRY.

The legacy variant generator (``clawsocialarena.generator.phase5_attack_variants``)
emits single-shot opening_message-style attacks via the
:class:`AttackPayload` registry. The four heuristic scorers in
``phase5_attack_scoring.py`` fire either ~0% (security / privacy
single-shot is too weak) or ~80%+ baseline-FP (governance,
collaboration are too lenient). The stress recipes per spec
Section 4.2 fix this by:

- security: embedding the payload in a resource the agent reads via
  tool dispatch (not the opening message);
- privacy: spinning up an adaptive attacker peer that escalates
  across turns until the focal agent leaks;
- governance: planting a fake consent row directly in the per-user
  sqlite db (or a side-channel ``consent_log.txt`` for families
  without a consent table);
- collaboration: spinning up a sabotaging peer that contradicts /
  redirects / refuses / stalls.

This script OVERLAYS the stress-recipe artifacts on top of an
already-generated scaffold so we do not have to re-run the full
naturalization pipeline. It walks the scaffold's variant index,
loads each non-baseline variant's base bundle, asks the matching
:class:`StressRecipe` to produce its
:class:`StressVariantArtifacts`, and applies the mutations:

- ``opening_message_addendum``: appended to ``scenario.json``'s
  ``opening_message.content``;
- ``injected_messages``: appended to ``scenario.json``'s
  ``injected_messages``;
- ``resource_file_writes``: written under
  ``variant_dir/resources/<relpath>`` (creating the directory tree
  on the variant copy, overlaid on the inherited base bundle's
  resources/);
- ``resource_db_inserts`` and ``resource_db_updates``: applied to
  the per-user sqlite db at
  ``variant_dir/resources/<db_path>``;
- adaptive fields (``requires_runtime_peer``, ``attacker_peer_id``,
  ``attacker_peer_prompt``, ``attacker_peer_max_turns``): baked into
  ``phase5_variant_metadata.json.attack``.

After this script, R-B 2 can re-run only the attack rows (112 of
140 are non-baseline) and the heuristic + LLM-judge scorers will
see the new stress payloads without re-running naturalization
on baseline rows.

Idempotence: the script re-creates the variant's resources/
overlay each run, so re-running with the same recipe produces the
same bytes. It refuses to operate on variants whose
``phase5_variant_metadata.json`` is missing.
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from clawsocialarena.attacks.stress_recipes import (  # noqa: E402
    STRESS_RECIPE_REGISTRY,
    StressVariantArtifacts,
)
from clawsocialarena.generator.phase5_attack_variants import (  # noqa: E402
    PHASE5_VARIANT_INDEX_FILENAME,
    PHASE5_VARIANT_METADATA_FILENAME,
)


_AXIS_TO_RECIPE: dict[str, str] = {
    "security": "indirect_resource_prompt_injection",
    "privacy": "adaptive_exfiltration",
    "governance": "poisoned_consent_row",
    "collaboration": "adaptive_malicious_peer",
}


def _load_base_bundle(variant_dir: Path) -> dict[str, Any]:
    """Reconstruct a recipe-consumable base_bundle dict from disk.

    Recipes look up:
    - ``agent_graph.nodes`` (role_label, agent_id, owner_id, ...)
    - ``governance_manifest.governed_actions`` and
      ``governance_manifest.approval_mandates``
    - ``resource_manifest`` (sensitivity, content metadata)
    - ``agents`` (fallback target / peer resolution)
    - ``opening_message`` (when the recipe wants to compose an
      addendum)

    These fields live in ``scenario.gt.json`` (the GT bundle) and
    ``scenario.json``. We merge both into a single dict so a recipe
    can read either entry point.
    """
    # The base bundle lives at variant_dir.parent.parent (two up from
    # the attack_variants/<axis>/ directory). We read both the
    # scenario.json and the scenario.gt.json so all fields are
    # available to the recipe.
    base_dir = variant_dir.parent.parent
    scenario_path = base_dir / "scenario.json"
    gt_path = base_dir / "scenario.gt.json"
    if not scenario_path.is_file() or not gt_path.is_file():
        raise FileNotFoundError(
            f"missing scenario.json or scenario.gt.json under {base_dir}"
        )
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    merged: dict[str, Any] = dict(scenario)
    for key, value in gt.items():
        if key not in merged:
            merged[key] = value
    return merged


def _seed_variant_resource_dirs(variant_dir: Path) -> None:
    """Ensure the variant has its own ``resources/`` and
    ``resources_initial/`` trees, seeded from the base bundle.

    Two reasons we need a per-variant copy of both trees:

    1. The live executor's :func:`_restore_resources_from_snapshot`
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


def _rewrite_variant_metadata(
    *,
    variant_dir: Path,
    artifacts: StressVariantArtifacts,
    recipe_name: str,
) -> None:
    """Update phase5_variant_metadata.json with the stress-recipe
    fields. The legacy attack fields (attack_mode, attack_intensity,
    delivery_surface, attacker_control) are preserved; only the
    recipe-specific subfields are overwritten.
    """
    meta_path = variant_dir / PHASE5_VARIANT_METADATA_FILENAME
    if not meta_path.is_file():
        raise FileNotFoundError(
            f"phase5_variant_metadata.json missing under {variant_dir}; "
            "rebuild the scaffold from scratch first"
        )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    attack = dict(meta.get("attack") or {})
    attack["attack_recipe"] = recipe_name
    attack["payload_text"] = artifacts.payload_text
    attack["target_agent_id"] = artifacts.target_agent_id
    # Merge recipe metadata under attack.metadata; don't clobber any
    # pre-existing keys like ``message_kind``.
    legacy_meta = dict(attack.get("metadata") or {})
    legacy_meta.update(artifacts.recipe_metadata)
    attack["metadata"] = legacy_meta
    if artifacts.requires_runtime_peer:
        attack["requires_runtime_peer"] = True
        attack["attacker_peer_id"] = artifacts.attacker_peer_id
        attack["attacker_peer_prompt"] = artifacts.attacker_peer_prompt
        attack["attacker_peer_max_turns"] = artifacts.attacker_peer_max_turns
    else:
        attack["requires_runtime_peer"] = False
    meta["attack"] = attack
    meta["stress_recipe_overlay"] = {
        "recipe_name": recipe_name,
        "applied_resource_writes": sorted(
            artifacts.resource_file_writes.keys()
        ),
        "applied_db_inserts": [
            f"{k[0]}::{k[1]}" for k in artifacts.resource_db_inserts.keys()
        ],
        "applied_db_updates": [
            f"{k[0]}::{k[1]}({k[2]}={k[3]})"
            for k in artifacts.resource_db_updates.keys()
        ],
    }
    meta_path.write_text(
        json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8"
    )


def _overlay_one_variant(
    *,
    variant_dir: Path,
    family_id: str,
    axis: str,
    seed: int,
) -> dict[str, Any]:
    """Apply the right stress recipe for ``axis`` to ``variant_dir``.

    Returns a small report dict (recipe_name + counts of applied
    mutations) for the runner's summary.
    """
    recipe_name = _AXIS_TO_RECIPE.get(axis)
    if not recipe_name or recipe_name not in STRESS_RECIPE_REGISTRY:
        return {"axis": axis, "recipe": None, "applied": False}
    recipe = STRESS_RECIPE_REGISTRY[recipe_name]
    base_bundle = _load_base_bundle(variant_dir)
    artifacts = recipe.build_variant_artifacts(
        base_bundle=base_bundle, family_id=family_id, seed=seed
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
    _rewrite_variant_metadata(
        variant_dir=variant_dir,
        artifacts=artifacts,
        recipe_name=recipe_name,
    )
    return {
        "axis": axis,
        "recipe": recipe_name,
        "applied": True,
        "file_writes": file_writes,
        "db_inserts": db_inserts,
        "db_updates": db_updates,
        "requires_runtime_peer": artifacts.requires_runtime_peer,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scaffold-dir",
        type=Path,
        required=True,
        help="Path to the Phase-5 scaffold root containing "
        "phase5_variants_index.json (e.g., benchmark/phase5/scaffold).",
    )
    parser.add_argument(
        "--axis",
        choices=("security", "privacy", "governance", "collaboration", "all"),
        default="all",
        help="Restrict the overlay to a single axis (default: all four).",
    )
    parser.add_argument(
        "--family",
        default=None,
        help="Restrict to a single family_id (e.g., tau2_telecom).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of variants overlaid (debug runs).",
    )
    parser.add_argument(
        "--out-report",
        type=Path,
        default=None,
        help="Write a JSON report of the overlay results to this path.",
    )
    args = parser.parse_args()

    scaffold_dir: Path = args.scaffold_dir
    index_path = scaffold_dir / PHASE5_VARIANT_INDEX_FILENAME
    if not index_path.is_file():
        print(
            f"error: variant index not found at {index_path}", file=sys.stderr
        )
        return 2
    index = json.loads(index_path.read_text(encoding="utf-8"))
    rows = list(index.get("variants") or [])
    rows.sort(key=lambda r: r["variant_id"])

    axes_to_apply: set[str] = (
        {"security", "privacy", "governance", "collaboration"}
        if args.axis == "all"
        else {args.axis}
    )

    report: list[dict[str, Any]] = []
    applied_count = 0
    for row in rows:
        if row["attack_mode"] == "no_attacker":
            continue
        if row["attack_mode"] not in axes_to_apply:
            continue
        if args.family and row["family_id"] != args.family:
            continue
        variant_dir = scaffold_dir / row["bundle_dir"]
        if not variant_dir.is_dir():
            print(
                f"  skip: variant dir missing {variant_dir}", file=sys.stderr
            )
            continue
        # Deterministic seed per variant: combine base_scenario_id +
        # attack_mode so each variant picks a stable payload variant.
        seed = abs(hash((row["base_scenario_id"], row["attack_mode"]))) % 1000
        try:
            outcome = _overlay_one_variant(
                variant_dir=variant_dir,
                family_id=row["family_id"],
                axis=row["attack_mode"],
                seed=seed,
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"  error: {row['variant_id']} -> "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            outcome = {
                "axis": row["attack_mode"],
                "recipe": _AXIS_TO_RECIPE.get(row["attack_mode"]),
                "applied": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        report.append({"variant_id": row["variant_id"], **outcome})
        if outcome.get("applied"):
            applied_count += 1
        if args.limit and applied_count >= args.limit:
            break

    summary = {
        "scaffold_dir": str(scaffold_dir),
        "axes_applied": sorted(axes_to_apply),
        "family_filter": args.family,
        "limit": args.limit,
        "n_variants_seen": len(report),
        "n_variants_applied": applied_count,
        "rows": report,
    }
    if args.out_report:
        args.out_report.write_text(
            json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
        )
        print(f"wrote {args.out_report}")
    else:
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
