"""Cell-aware base-task generator for the Phase-5 pilot (S3 step 3).

Walks the 14-cell allocation × 3 task variants matrix and
materializes each combination into a deterministic bundle directory.
Every bundle on disk also carries a ``phase5_metadata.json`` sidecar
capturing the cell coordinate, task variant, and attack intensity so
the downstream attack-variant injector and run-batch orchestrator
can recover the context without re-deriving it.

v2 math (difficulty-tier dimension dropped; stress-recipe attacks
carry the difficulty pressure that tiers previously did):

    14 cells × 3 task variants = 42 base bundles

This module is the only authority that decides where on disk each
bundle lands; the orchestrator and the attack-variant injector both
consume :func:`generate_base_bundles` (or load its
``phase5_base_index.json`` output) so a path change here propagates
everywhere.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from clawsocialarena.generator.cell_allocation import CellSpec, all_cells
from clawsocialarena.generator.difficulty_tier import (
    TierSpec,
    apply_tier,
    bargaining_window_kwargs,
)
from clawsocialarena.generator.family_pack_registry import load_and_materialize
from clawsocialarena.generator.phase5_task_variants import (
    TaskVariantSpec,
    task_variants_for,
)


PHASE5_METADATA_FILENAME = "phase5_metadata.json"
PHASE5_BASE_INDEX_FILENAME = "phase5_base_index.json"

TASK_INDICES: tuple[int, ...] = (0, 1, 2)
TIER_INDICES: tuple[int, ...] = (1, 2, 3)


@dataclass(frozen=True)
class BaseBundleRecord:
    """One row in the base-bundle index produced by :func:`generate_base_bundles`.

    ``base_scenario_id`` is the canonical identifier carried into the
    attack-variant table so each of the 5 attack modes can be tied
    back to the unique base bundle it was generated from.
    """

    cell_index: int
    cell_id: str
    category: str
    slot: str
    family_id: str
    task_index: int
    task_label: str
    # Legacy difficulty-tier fields, kept Optional for one release after
    # the tier dimension was collapsed; new records carry ``None``.
    tier_index: int | None
    tier_name: str | None
    attack_intensity: float
    base_scenario_id: str
    bundle_dir: str  # relative to the generator out_dir
    loader_kwargs: dict[str, Any] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)


def _format_base_scenario_id(
    cell: CellSpec, task_index: int, *, tier_index: int | None
) -> str:
    """Return the canonical id for a base bundle.

    Format: ``{cell_id}__t{task_index}`` after the tier dimension was
    dropped. When ``tier_index`` is provided (legacy callers), the
    ``__d{tier_index}`` suffix is appended; new callers should pass
    ``tier_index=None`` so the id matches the on-disk layout.
    """
    base = f"{cell.cell_id}__t{task_index}"
    if tier_index is not None:
        base = f"{base}__d{tier_index}"
    return base


def _bundle_subdir_for(
    cell: CellSpec, task_index: int, *, tier_index: int | None
) -> Path:
    """Return the per-bundle subdirectory relative to the generator root.

    When ``tier_index`` is ``None`` (current default), the layout is
    ``<cell_id>/task<task_index>``. The legacy three-level layout
    (``.../tier<n>``) is still produced when a caller passes an
    explicit ``tier_index`` so external tooling that has not migrated
    yet keeps working.
    """
    parts: list[str] = [cell.cell_id, f"task{task_index}"]
    if tier_index is not None:
        parts.append(f"tier{tier_index}")
    return Path(*parts)


def _maybe_narrow_bargaining_kwargs(
    family_id: str, kwargs: dict[str, Any], *, tier_index: int | None
) -> dict[str, Any]:
    """For marble_bargaining at tiers 2/3, narrow the window kwargs.

    With the difficulty-tier dim dropped, ``tier_index=None`` keeps
    the loader's default permissive window (matches tier-1 behavior).
    All other families return ``kwargs`` unchanged. Returns a fresh
    dict so the caller's variant table is not mutated.
    """
    out = dict(kwargs)
    if family_id != "marble_bargaining" or tier_index is None:
        return out
    market_reference_price = float(out.get("market_reference_price") or 50.0)
    narrowed = bargaining_window_kwargs(
        market_reference_price=market_reference_price, tier_index=tier_index
    )
    if narrowed is not None:
        out.update(narrowed)
    return out


def _apply_tier_overrides_to_scenario_file(
    *, bundle_dir: Path, family_id: str, tier_index: int
) -> tuple[TierSpec, dict[str, Any], dict[str, Any]]:
    """Apply tier transformations to the materialized scenario.json.

    Returns ``(tier_spec, scenario_overrides, per_pack_extras)`` so the
    caller can include the same information in ``phase5_metadata.json``.
    """
    scenario_path = bundle_dir / "scenario.json"
    if not scenario_path.is_file():
        raise FileNotFoundError(
            f"scenario.json not found at {scenario_path}; "
            "materializer did not produce the expected bundle"
        )
    scenario_dict = json.loads(scenario_path.read_text(encoding="utf-8"))
    tier_result = apply_tier(
        family_id=family_id,
        scenario_dict=scenario_dict,
        tier_index=tier_index,
    )
    if tier_result.scenario_overrides:
        scenario_dict.update(tier_result.scenario_overrides)
        scenario_path.write_text(
            json.dumps(scenario_dict, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return (
        tier_result.tier,
        dict(tier_result.scenario_overrides),
        dict(tier_result.metadata.get("per_pack_extras", {})),
    )


def _write_phase5_sidecar(
    *,
    bundle_dir: Path,
    record: BaseBundleRecord,
    scenario_overrides: dict[str, Any],
) -> None:
    """Write the per-bundle phase5_metadata.json sidecar.

    The sidecar is consumed by:
    - the attack-variant injector (to know the attack_intensity per
      base bundle)
    - the orchestrator (to know which cell this bundle belongs to
      without re-parsing the path)

    ``per_pack_extras`` is sourced from ``record.extras`` so the
    caller does not have to thread it through a separate kwarg.
    """
    per_pack_extras = dict(record.extras.get("per_pack_extras") or {})
    payload = {
        "phase5_version": 1,
        "cell": {
            "cell_index": record.cell_index,
            "cell_id": record.cell_id,
            "category": record.category,
            "slot": record.slot,
            "family_id": record.family_id,
        },
        "task_variant": {
            "task_index": record.task_index,
            "task_label": record.task_label,
            "loader_kwargs": record.loader_kwargs,
        },
        "tier": {
            "tier_index": record.tier_index,
            "tier_name": record.tier_name,
            "attack_intensity": record.attack_intensity,
            "scenario_overrides": scenario_overrides,
            "per_pack_extras": per_pack_extras,
        },
        "base_scenario_id": record.base_scenario_id,
    }
    sidecar = bundle_dir / PHASE5_METADATA_FILENAME
    sidecar.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )


def generate_base_bundles(
    *,
    out_dir: Path | str,
    cells: tuple[CellSpec, ...] | None = None,
    task_indices: tuple[int, ...] = TASK_INDICES,
    tier_indices: tuple[int, ...] | None = None,
) -> list[BaseBundleRecord]:
    """Materialize the (cell × task) base bundles to ``out_dir``.

    Returns a list of :class:`BaseBundleRecord` in canonical iteration
    order (cell_index ascending, task_index ascending). The
    difficulty-tier dimension was collapsed in v2; ``tier_indices`` is
    accepted for backward compatibility but ignored. Each (cell, task)
    pair always materializes the easy/tier-1 baseline.

    Also writes ``phase5_base_index.json`` at the top of ``out_dir``
    so downstream tools can load the index without re-running the
    generator.
    """
    # ``tier_indices`` is intentionally ignored: the difficulty-tier
    # dimension was dropped in v2. The kwarg stays in the signature so
    # callers that pass it can be updated incrementally.
    _ = tier_indices

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    target_cells = cells if cells is not None else all_cells()
    records: list[BaseBundleRecord] = []
    # Per-family variant tables are cached so we do not rebuild them
    # 14*3 times.
    variants_cache: dict[str, tuple[TaskVariantSpec, ...]] = {}

    for cell in target_cells:
        if cell.family_id not in variants_cache:
            variants_cache[cell.family_id] = task_variants_for(cell.family_id)
        variants = variants_cache[cell.family_id]
        for task_index in task_indices:
            if not 0 <= task_index < len(variants):
                raise IndexError(
                    f"task_index {task_index} out of range for "
                    f"family_id={cell.family_id!r}"
                )
            variant = variants[task_index]
            # The difficulty-tier dimension was collapsed in v2: we
            # always materialize the easy/tier-1 baseline (no opening
            # message pressure, full turn budget) and rely on the
            # stress-recipe attack vectors for difficulty pressure.
            sub_dir = _bundle_subdir_for(cell, task_index, tier_index=None)
            bundle_target_dir = out_path / sub_dir
            bundle_target_dir.parent.mkdir(parents=True, exist_ok=True)
            tier_kwargs = _maybe_narrow_bargaining_kwargs(
                cell.family_id, variant.loader_kwargs, tier_index=None
            )
            bundle_dir, _bundle = load_and_materialize(
                family_id=cell.family_id,
                out_dir=bundle_target_dir,
                load_kwargs=tier_kwargs,
            )
            (
                tier_applied,
                scenario_overrides,
                per_pack_extras,
            ) = _apply_tier_overrides_to_scenario_file(
                bundle_dir=bundle_dir,
                family_id=cell.family_id,
                tier_index=1,
            )
            record = BaseBundleRecord(
                cell_index=cell.cell_index,
                cell_id=cell.cell_id,
                category=cell.category,
                slot=cell.slot,
                family_id=cell.family_id,
                task_index=task_index,
                task_label=variant.label,
                tier_index=None,  # legacy field; kept on the dataclass for one release
                tier_name=None,
                attack_intensity=tier_applied.attack_intensity,
                base_scenario_id=_format_base_scenario_id(
                    cell, task_index, tier_index=None
                ),
                bundle_dir=str(bundle_dir.relative_to(out_path)),
                loader_kwargs=dict(tier_kwargs),
                extras={"per_pack_extras": per_pack_extras},
            )
            _write_phase5_sidecar(
                bundle_dir=bundle_dir,
                record=record,
                scenario_overrides=scenario_overrides,
            )
            records.append(record)

    index_path = out_path / PHASE5_BASE_INDEX_FILENAME
    index_path.write_text(
        json.dumps(
            {
                "phase5_version": 1,
                "n_cells": len(target_cells),
                "n_task_indices": len(task_indices),
                # ``n_tier_indices`` stays in the schema for one
                # release at 0 so consumers can detect the v2 layout
                # without immediate code changes.
                "n_tier_indices": 0,
                "n_records": len(records),
                "records": [asdict(r) for r in records],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return records


def load_base_index(index_path: Path | str) -> list[BaseBundleRecord]:
    """Reload the base-bundle records written by :func:`generate_base_bundles`.

    Tolerates both v1 records (which carried mandatory ``tier_index`` /
    ``tier_name``) and v2 records (which carry ``None``).
    """
    raw = json.loads(Path(index_path).read_text(encoding="utf-8"))
    return [
        BaseBundleRecord(
            cell_index=row["cell_index"],
            cell_id=row["cell_id"],
            category=row["category"],
            slot=row["slot"],
            family_id=row["family_id"],
            task_index=row["task_index"],
            task_label=row["task_label"],
            tier_index=row.get("tier_index"),
            tier_name=row.get("tier_name"),
            attack_intensity=row["attack_intensity"],
            base_scenario_id=row["base_scenario_id"],
            bundle_dir=row["bundle_dir"],
            loader_kwargs=dict(row.get("loader_kwargs") or {}),
            extras=dict(row.get("extras") or {}),
        )
        for row in raw["records"]
    ]
