"""Phase-5 manifest assembly (S3 step 7).

Aggregates the 465 main attack-variants and the 50 supplementary
descriptors into a single ``phase5_manifest.json`` index. The
orchestrator's Run-Batch 1..5 selectors consult this file by stratum,
attack_mode, and cell to determine which rows belong to a given
batch.

v2 math (difficulty-tier dim dropped, MARBLE bargaining expanded):

    3 marble_research cells × 8 tasks × 5 attack modes = 120
    2 marble_bargaining cells × 12 tasks × 5 attack modes = 120
    2 marble_bidding cells × 6 tasks × 5 attack modes = 60
    11 other cells × 3 tasks × 5 attack modes = 165
    Total main: 465 main variants
    + 50 supplementary descriptors
    = 515 total rows

Manifest schema (top level):

    {
      "phase5_version": 1,
      "n_main": 465,
      "n_supplementary": 50,
      "n_total": 515,
      "main": [<MainManifestRow>...],
      "supplementary": [<SupplementaryManifestRow>...]
    }

A main row carries every key the orchestrator needs without having
to re-read the on-disk sidecar; a supplementary row carries the
SupplementaryRecord fields plus a stable canonical_index.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from clawsocialarena.generator.phase5_attack_variants import (
    PHASE5_VARIANT_INDEX_FILENAME,
    VariantRecord,
    expand_base_records_to_variants,
    load_variant_index,
)
from clawsocialarena.generator.phase5_base_generator import (
    BaseBundleRecord,
    generate_base_bundles,
)
from clawsocialarena.generator.phase5_supplementary import (
    SupplementaryRecord,
    supplementary_records,
)


PHASE5_MANIFEST_FILENAME = "phase5_manifest.json"
# v2 counts (difficulty-tier dim dropped, MARBLE bargaining expanded):
#   3 marble_research cells × 8 × 5 = 120
#   2 marble_bargaining cells × 12 × 5 = 120
#   2 marble_bidding cells × 6 × 5 = 60
#   11 other cells × 3 × 5 = 165
#   Total: 465 main variants
EXPECTED_MAIN_VARIANTS = 465
EXPECTED_SUPPLEMENTARY_VARIANTS = 50
EXPECTED_TOTAL_VARIANTS = EXPECTED_MAIN_VARIANTS + EXPECTED_SUPPLEMENTARY_VARIANTS


@dataclass(frozen=True)
class MainManifestRow:
    """One row of the main stratum manifest.

    Mirrors :class:`VariantRecord` fields plus a canonical_index for
    stable ordering. ``attack_mode`` is the spec section 2 axis
    (no_attacker / collaboration / security / privacy / governance);
    ``attack_recipe`` carries the concrete tactic.
    """

    canonical_index: int  # 0..(EXPECTED_MAIN_VARIANTS-1)
    variant_id: str
    base_scenario_id: str
    cell_id: str
    family_id: str
    task_index: int
    # Legacy difficulty-tier field; ``None`` on v2 manifests (the tier
    # dimension was dropped). Kept on the dataclass for one release.
    tier_index: int | None
    attack_mode: str
    attack_intensity: float
    attack_recipe: str | None
    delivery_surface: str | None
    attacker_control: str | None
    target_agent_id: str | None
    bundle_dir: str
    attack_metadata: dict[str, Any]
    stratum: str = "main"


@dataclass(frozen=True)
class SupplementaryManifestRow:
    """One row of the 50-row supplementary stratum manifest."""

    canonical_index: int  # 0..49
    variant_id: str
    sub_stratum: str
    sub_index: int
    recipe: str
    family_id: str | None
    description: str
    parameters: dict[str, Any]
    stratum: str = "supplementary"


def _variants_to_manifest_rows(
    variants: list[VariantRecord],
) -> list[MainManifestRow]:
    rows: list[MainManifestRow] = []
    for index, variant in enumerate(variants):
        rows.append(
            MainManifestRow(
                canonical_index=index,
                variant_id=variant.variant_id,
                base_scenario_id=variant.base_scenario_id,
                cell_id=variant.cell_id,
                family_id=variant.family_id,
                task_index=variant.task_index,
                tier_index=variant.tier_index,
                attack_mode=variant.attack_mode,
                attack_intensity=variant.attack_intensity,
                attack_recipe=variant.attack_recipe,
                delivery_surface=variant.delivery_surface,
                attacker_control=variant.attacker_control,
                target_agent_id=variant.target_agent_id,
                bundle_dir=variant.bundle_dir,
                attack_metadata=dict(variant.attack_metadata),
            )
        )
    return rows


def _supp_records_to_manifest_rows(
    records: list[SupplementaryRecord],
) -> list[SupplementaryManifestRow]:
    rows: list[SupplementaryManifestRow] = []
    for index, record in enumerate(records):
        rows.append(
            SupplementaryManifestRow(
                canonical_index=index,
                variant_id=record.variant_id,
                sub_stratum=record.sub_stratum,
                sub_index=record.sub_index,
                recipe=record.recipe,
                family_id=record.family_id,
                description=record.description,
                parameters=dict(record.parameters),
            )
        )
    return rows


def assemble_manifest(
    *,
    out_dir: Path | str,
    base_records: list[BaseBundleRecord] | None = None,
    reuse_existing_variant_index: bool = False,
) -> dict[str, Any]:
    """Build (or re-build) the Phase-5 manifest under ``out_dir``.

    If ``base_records`` is provided, the manifest is built from those
    records and ``expand_base_records_to_variants`` is called fresh
    -- the existing ``phase5_variants_index.json`` is unconditionally
    overwritten so a partial rebuild never picks up stale rows from a
    prior full build (the codex Batch S3 review caught this drift
    risk).

    Set ``reuse_existing_variant_index=True`` only when the caller
    has just-finished writing the index and wants to skip the
    expansion pass (used by tests).

    If ``base_records`` is ``None``, the function materializes the
        full 93-base x 5-mode = 465-variant main set into ``out_dir``
    from scratch.

    Writes ``phase5_manifest.json`` at ``out_dir`` and returns the
    same payload as a Python dict.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if base_records is None:
        base_records = generate_base_bundles(out_dir=out_path)

    variant_index = out_path / PHASE5_VARIANT_INDEX_FILENAME
    if reuse_existing_variant_index and variant_index.is_file():
        variants = load_variant_index(variant_index)
    else:
        variants = expand_base_records_to_variants(
            base_records=base_records, base_dir=out_path
        )

    main_rows = _variants_to_manifest_rows(variants)
    if len(main_rows) != EXPECTED_MAIN_VARIANTS:
        raise ValueError(
            f"main variants {len(main_rows)} != expected {EXPECTED_MAIN_VARIANTS}"
        )
    supp_rows = _supp_records_to_manifest_rows(supplementary_records())
    if len(supp_rows) != EXPECTED_SUPPLEMENTARY_VARIANTS:
        raise ValueError(
            f"supplementary rows {len(supp_rows)} != expected "
            f"{EXPECTED_SUPPLEMENTARY_VARIANTS}"
        )

    manifest = {
        "phase5_version": 1,
        "n_main": len(main_rows),
        "n_supplementary": len(supp_rows),
        "n_total": len(main_rows) + len(supp_rows),
        "main": [asdict(r) for r in main_rows],
        "supplementary": [asdict(r) for r in supp_rows],
    }
    (out_path / PHASE5_MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest


def select_rows(
    manifest: dict[str, Any],
    *,
    stratum: str | None = None,
    cell_id: str | None = None,
    family_id: str | None = None,
    tier_index: int | None = None,
    task_index: int | None = None,
    attack_mode: str | None = None,
    sub_stratum: str | None = None,
) -> list[dict[str, Any]]:
    """Filter the manifest rows by any subset of fields.

    The orchestrator's canonical Run-Batch selectors live in
    :mod:`clawsocialarena.orchestrator.phase5_run_batches`; this helper
    is a lower-level field filter used by tests and reports.
    """
    rows: list[dict[str, Any]] = []
    pools: list[list[dict[str, Any]]] = []
    if stratum in (None, "main"):
        pools.append(manifest.get("main", []))
    if stratum in (None, "supplementary"):
        pools.append(manifest.get("supplementary", []))
    for pool in pools:
        for row in pool:
            if cell_id is not None and row.get("cell_id") != cell_id:
                continue
            if family_id is not None and row.get("family_id") != family_id:
                continue
            if tier_index is not None and row.get("tier_index") != tier_index:
                continue
            if task_index is not None and row.get("task_index") != task_index:
                continue
            if attack_mode is not None and row.get("attack_mode") != attack_mode:
                continue
            if sub_stratum is not None and row.get("sub_stratum") != sub_stratum:
                continue
            rows.append(row)
    return rows


def load_manifest(path: Path | str) -> dict[str, Any]:
    """Reload a previously written ``phase5_manifest.json``."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
