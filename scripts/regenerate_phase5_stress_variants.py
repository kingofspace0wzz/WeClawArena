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
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from clawsocialarena.attacks.runtime_overlay import _recipe_name_for  # noqa: E402
from clawsocialarena.attacks.stress_recipes import (  # noqa: E402
    StressVariantArtifacts,
)
from clawsocialarena.generator.phase5_attack_variants import (  # noqa: E402
    PHASE5_VARIANT_INDEX_FILENAME,
    PHASE5_VARIANT_METADATA_FILENAME,
)


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
    context_path = base_dir / "family_pack_context.json"
    if context_path.is_file():
        try:
            context = json.loads(context_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            context = None
        if isinstance(context, dict):
            merged["family_pack_context"] = context
    return merged


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
    attack["attack_recipe"] = artifacts.recipe_metadata.get(
        "attack_recipe", recipe_name
    )
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

    Thin wrapper around
    :func:`clawsocialarena.attacks.runtime_overlay.apply_recipe_to_variant_dir`
    that preserves the CLI's report-summary shape and handles the
    scaffold-specific :func:`_rewrite_variant_metadata` step.

    Returns a small report dict (recipe_name + counts of applied
    mutations) for the runner's summary.
    """
    from clawsocialarena.attacks.runtime_overlay import apply_recipe_to_variant_dir

    base_bundle = _load_base_bundle(variant_dir)
    outcome = apply_recipe_to_variant_dir(
        variant_dir=variant_dir,
        attack_mode=axis,
        base_bundle=base_bundle,
        family_id=family_id,
        seed=seed,
    )
    if not outcome.get("applied"):
        return {"axis": axis, "recipe": None, "applied": False}
    artifacts = outcome.pop("_artifacts")
    recipe_name = outcome["recipe"]
    _rewrite_variant_metadata(
        variant_dir=variant_dir,
        artifacts=artifacts,
        recipe_name=recipe_name,
    )
    return {"axis": axis, **outcome}


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
                "recipe": _recipe_name_for(
                    family_id=row["family_id"],
                    attack_mode=row["attack_mode"],
                ),
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
