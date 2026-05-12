"""Family-pack skeleton builder for the Phase-5 naturalization pipeline.

The existing :mod:`clawsocialarena.generator.naturalization` accepts a
``skeleton_payload`` dict and asks gpt-5.2 to fill in a
``NaturalizationPatch``. The worldpack pipeline assembled skeletons from
``index_row`` plus the per-scenario ``scenario.json`` / ``scenario.gt.json``
files (see :func:`scripts.naturalize_and_run_batch.build_skeleton_payload`).

Family packs use the same ``scenario.json`` / ``scenario.gt.json``
contract but drop ``terminal_predicate`` in favor of
``evaluation_criteria`` and add ``family_pack_context.json`` next to
the bundle. This module produces a skeleton payload from a family-pack
bundle dir that the same naturalization machinery can consume.

Two callers will use this module:

- Phase-5 S3 generators -- when emitting scenario manifests, they call
  :func:`build_family_pack_skeleton` to record the canonical payload
  the run-batch will hand to gpt-5.2.
- Phase-5 S4 orchestrator -- at run time, it calls the same builder to
  reproduce the same skeleton deterministically for each scenario.

Keeping both flows on one builder eliminates the drift risk codex
flagged in Batch A: every scenario's naturalization input is computed
the same way regardless of caller.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clawsocialarena.generator.family_pack_registry import FAMILY_LOADERS


@dataclass(frozen=True)
class FamilyPackSkeleton:
    """The naturalization-pipeline-ready skeleton for one family-pack bundle.

    ``payload`` is the dict the gpt-5.2 naturalizer receives. ``bundle_dir``
    is the materialized bundle on disk. ``family_id`` is the canonical
    pack id; ``cell_id`` is the optional Phase-5 cell label for
    cross-referencing the run-batch report.
    """

    family_id: str
    bundle_dir: Path
    cell_id: str | None
    payload: dict[str, Any]


def build_family_pack_skeleton(
    *,
    family_id: str,
    bundle_dir: Path | str,
    cell_id: str | None = None,
    index_row: dict[str, Any] | None = None,
) -> FamilyPackSkeleton:
    """Read a materialized family-pack bundle and produce a skeleton
    payload the naturalization pipeline can consume.

    The returned payload mirrors the worldpack ``skeleton_payload``
    shape so the existing :func:`run_naturalization` accepts it
    unchanged, with two family-pack-specific additions:

    - ``evaluation_criteria`` is lifted from ``scenario.gt.json`` and
      surfaced at the top level (replaces ``terminal_predicate`` for
      family-pack scenarios).
    - ``family_pack`` carries the registry entry's
      ``naturalization_hints`` + the ``family_pack_context.json`` so
      gpt-5.2 sees domain guidance + identity-binding context.
    """
    if family_id not in FAMILY_LOADERS:
        raise KeyError(
            f"unknown family_id={family_id!r}; "
            f"registered ids: {sorted(FAMILY_LOADERS.keys())}"
        )
    entry = FAMILY_LOADERS[family_id]
    bundle_path = Path(bundle_dir)
    scenario = _read_json(bundle_path / "scenario.json")
    gt = _read_json(bundle_path / "scenario.gt.json")
    family_pack_context = _read_json(bundle_path / "family_pack_context.json")

    construction = gt.get("construction_manifest")
    payload: dict[str, Any] = {
        "index_row": dict(index_row) if index_row else {},
        "scenario": scenario,
        "construction_manifest": construction,
        # Family-pack analog of terminal_predicate; the existing
        # naturalization module no-ops sanitization steps that key off
        # terminal_predicate when this field is absent, so leaving it
        # out is safe.
        "evaluation_criteria": gt.get("evaluation_criteria"),
        "resource_manifest": gt.get("resource_manifest"),
        "resource_payloads": _collect_resource_payloads(bundle_path),
        "governance_manifest": gt.get("governance_manifest"),
        "attack_plan": gt.get("attack_plan"),
        "invariants": gt.get("invariants"),
        "family_pack": {
            "family_id": family_id,
            "session_context_keys": list(entry.session_context_keys),
            "context": family_pack_context,
            "hints": dict(entry.naturalization_hints),
        },
    }
    return FamilyPackSkeleton(
        family_id=family_id,
        bundle_dir=bundle_path,
        cell_id=cell_id,
        payload=payload,
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _collect_resource_payloads(bundle_dir: Path) -> dict[str, Any]:
    """Slim resource snapshot for the naturalization payload.

    Family-pack resources live under ``resources/``; the
    naturalization pipeline benefits from seeing a small sample so the
    model can produce consistent prose without having to "discover"
    the entity surface. We surface only the human-readable JSON
    artifacts (orders.json / reservation.json / lines.json /
    family_pack_context.json) and stop short of dumping per-user
    SQLite blobs -- those land in the per-pack handlers at run time
    and would balloon the prompt.
    """
    resources_root = bundle_dir / "resources"
    if not resources_root.is_dir():
        return {}
    out: dict[str, Any] = {}
    for json_path in resources_root.rglob("*.json"):
        rel = str(json_path.relative_to(resources_root))
        # Skip Zone.Identifier sidecars and other non-payload files.
        if rel.endswith(".Zone.Identifier"):
            continue
        try:
            out[rel] = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
    return out
