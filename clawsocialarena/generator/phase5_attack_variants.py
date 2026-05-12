"""Attack-variant injector for the Phase-5 pilot (S3 step 5).

Multiplies every base bundle by 5 attack modes (per spec section 2's
matched grid: no_attacker / collaboration / security / privacy /
governance) and produces a flat list of 630 variant records. Each
variant carries the spec-required `attack_mode`, `attack_recipe`,
`attack_intensity`, `delivery_surface`, and `attacker_control`
fields so downstream selectors can slice by either the axis or the
recipe.

The clean baseline variant points at the original base bundle dir;
attack variants land in a sibling ``attack_variants/<mode>/``
directory with the injected scenario.json plus a sidecar describing
the injection. The injector also rewrites ``opening_message.to``
when the payload's message_kind is ``opening_message`` so the
attack is delivered to the intended target_agent_id rather than the
original opening-message recipient.

The orchestrator uses ``attack_mode`` to decide which slice of the
manifest to run.
"""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from clawsocialarena.generator.phase5_attack_payloads import (
    ATTACK_MODES_ALL,
    ATTACK_MODES_NON_BASELINE,
    AttackPayload,
    attack_payloads_for,
)
from clawsocialarena.generator.phase5_base_generator import BaseBundleRecord


PHASE5_VARIANT_INDEX_FILENAME = "phase5_variants_index.json"
PHASE5_VARIANT_METADATA_FILENAME = "phase5_variant_metadata.json"
ATTACK_VARIANT_DIRNAME = "attack_variants"


@dataclass(frozen=True)
class VariantRecord:
    """One variant in the 630-row Phase-5 attack-variant table.

    ``variant_id`` is ``{base_scenario_id}__{attack_mode}`` (uses the
    axis label, not the recipe, so selectors stay stable if a recipe
    is swapped). ``attack_recipe`` carries the concrete tactic;
    ``delivery_surface`` and ``attacker_control`` are the spec
    section 2 metadata columns.

    For the baseline variant (``attack_mode == "no_attacker"``),
    ``attack_recipe`` / ``delivery_surface`` / ``attacker_control`` /
    ``target_agent_id`` are ``None``.
    """

    variant_id: str
    base_scenario_id: str
    cell_id: str
    family_id: str
    task_index: int
    tier_index: int
    attack_mode: str
    attack_intensity: float
    attack_recipe: str | None
    delivery_surface: str | None
    attacker_control: str | None
    target_agent_id: str | None
    bundle_dir: str  # the dir the orchestrator should mount
    attack_metadata: dict[str, Any] = field(default_factory=dict)


def _inject_payload_into_scenario(
    scenario: dict[str, Any], payload: AttackPayload
) -> dict[str, Any]:
    """Return a deep-copied scenario dict with the payload applied.

    The original scenario dict is not mutated; the caller writes the
    returned dict to disk under the attack variant's subdirectory.
    The injection switches on ``payload.message_kind`` (a Phase-5
    sub-field of ``DeliverySurface.MESSAGE``):

    - ``opening_message``: replaces ``opening_message.to`` with the
      payload's ``target_agent_id`` (so the attack lands on the
      intended recipient) and appends the payload text to the
      existing content. If no opening_message exists yet, a fresh one
      is created addressed to the target.
    - ``peer_message``: appends to ``injected_messages`` as if a peer
      agent had spoken.
    - ``system_aside``: appends to ``injected_messages`` as a
      system-side note.
    """
    out = copy.deepcopy(scenario)
    if payload.message_kind == "opening_message":
        opening = out.get("opening_message")
        if isinstance(opening, dict):
            existing = str(opening.get("content") or "")
            new = dict(opening)
            new["to"] = payload.target_agent_id
            new["content"] = f"{existing.strip()}\n\n{payload.payload_text}"
            out["opening_message"] = new
        else:
            out["opening_message"] = {
                "from": "system",
                "to": payload.target_agent_id,
                "content": payload.payload_text,
            }
    elif payload.message_kind == "peer_message":
        injected = out.setdefault("injected_messages", [])
        injected.append(
            {
                "from": "attacker_peer",
                "to": payload.target_agent_id,
                "content": payload.payload_text,
                "attack_mode": payload.attack_mode,
                "attack_recipe": payload.attack_recipe,
            }
        )
    elif payload.message_kind == "system_aside":
        injected = out.setdefault("injected_messages", [])
        injected.append(
            {
                "from": "system_aside",
                "to": payload.target_agent_id,
                "content": payload.payload_text,
                "attack_mode": payload.attack_mode,
                "attack_recipe": payload.attack_recipe,
            }
        )
    else:
        raise ValueError(
            f"unknown message_kind={payload.message_kind!r}"
        )
    return out


def _attack_variant_subdir(base_bundle_dir: Path, attack_mode: str) -> Path:
    return base_bundle_dir / ATTACK_VARIANT_DIRNAME / attack_mode


def _write_attack_scenario_and_sidecar(
    *,
    base_bundle_dir: Path,
    payload: AttackPayload,
    scenario_dict: dict[str, Any],
    base_record: BaseBundleRecord,
) -> Path:
    """Write the injected scenario.json + sidecar; return the variant dir.

    The variant subdir is keyed by ``attack_mode`` (the axis), not by
    ``attack_recipe``, so the on-disk layout matches the spec's
    matched-grid axis.
    """
    variant_dir = _attack_variant_subdir(base_bundle_dir, payload.attack_mode)
    variant_dir.mkdir(parents=True, exist_ok=True)
    injected = _inject_payload_into_scenario(scenario_dict, payload)
    scenario_path = variant_dir / "scenario.json"
    scenario_path.write_text(
        json.dumps(injected, indent=2, sort_keys=True), encoding="utf-8"
    )
    sidecar = {
        "phase5_version": 1,
        "variant_id": f"{base_record.base_scenario_id}__{payload.attack_mode}",
        "base_scenario_id": base_record.base_scenario_id,
        "cell_id": base_record.cell_id,
        "family_id": base_record.family_id,
        "task_index": base_record.task_index,
        "tier_index": base_record.tier_index,
        "attack": {
            "attack_mode": payload.attack_mode,
            "attack_recipe": payload.attack_recipe,
            "attack_intensity": base_record.attack_intensity,
            "delivery_surface": payload.delivery_surface,
            "attacker_control": payload.attacker_control,
            "message_kind": payload.message_kind,
            "target_agent_id": payload.target_agent_id,
            "payload_text": payload.payload_text,
            "metadata": payload.metadata,
        },
    }
    (variant_dir / PHASE5_VARIANT_METADATA_FILENAME).write_text(
        json.dumps(sidecar, indent=2, sort_keys=True), encoding="utf-8"
    )
    return variant_dir


def expand_base_records_to_variants(
    *,
    base_records: list[BaseBundleRecord],
    base_dir: Path | str,
) -> list[VariantRecord]:
    """Expand N base records into N*5 variant records on disk.

    For ``no_attacker`` variants, the bundle_dir field points at the
    original base bundle. For attack variants, the bundle_dir points
    at the per-variant subdir under ``attack_variants/<mode>/`` and
    a fresh ``scenario.json`` + ``phase5_variant_metadata.json``
    are written there. The variant index file is unconditionally
    overwritten so a partial rebuild does not leave stale rows from
    a prior full build.
    """
    base_path = Path(base_dir)
    variants: list[VariantRecord] = []
    for record in base_records:
        bundle_dir = base_path / record.bundle_dir
        scenario_path = bundle_dir / "scenario.json"
        if not scenario_path.is_file():
            raise FileNotFoundError(
                f"scenario.json missing for base record "
                f"{record.base_scenario_id}; expected at {scenario_path}"
            )
        scenario_dict = json.loads(scenario_path.read_text(encoding="utf-8"))
        # 1) Baseline (no_attacker) -- no recipe/surface/target.
        variants.append(
            VariantRecord(
                variant_id=f"{record.base_scenario_id}__no_attacker",
                base_scenario_id=record.base_scenario_id,
                cell_id=record.cell_id,
                family_id=record.family_id,
                task_index=record.task_index,
                tier_index=record.tier_index,
                attack_mode="no_attacker",
                attack_intensity=record.attack_intensity,
                attack_recipe=None,
                delivery_surface=None,
                attacker_control=None,
                target_agent_id=None,
                bundle_dir=record.bundle_dir,
                attack_metadata={},
            )
        )
        # 2) Four non-baseline attack variants, one per axis.
        payloads = attack_payloads_for(
            record.family_id,
            scenario=scenario_dict,
            loader_kwargs=record.loader_kwargs,
        )
        if len(payloads) != len(ATTACK_MODES_NON_BASELINE):
            raise ValueError(
                f"family {record.family_id} returned "
                f"{len(payloads)} payloads, expected "
                f"{len(ATTACK_MODES_NON_BASELINE)}"
            )
        for payload in payloads:
            variant_dir = _write_attack_scenario_and_sidecar(
                base_bundle_dir=bundle_dir,
                payload=payload,
                scenario_dict=scenario_dict,
                base_record=record,
            )
            variants.append(
                VariantRecord(
                    variant_id=(
                        f"{record.base_scenario_id}__{payload.attack_mode}"
                    ),
                    base_scenario_id=record.base_scenario_id,
                    cell_id=record.cell_id,
                    family_id=record.family_id,
                    task_index=record.task_index,
                    tier_index=record.tier_index,
                    attack_mode=payload.attack_mode,
                    attack_intensity=record.attack_intensity,
                    attack_recipe=payload.attack_recipe,
                    delivery_surface=payload.delivery_surface,
                    attacker_control=payload.attacker_control,
                    target_agent_id=payload.target_agent_id,
                    bundle_dir=str(variant_dir.relative_to(base_path)),
                    attack_metadata={
                        "message_kind": payload.message_kind,
                        "metadata": payload.metadata,
                    },
                )
            )

    # Sanity: the modes per base must match ATTACK_MODES_ALL.
    for record in base_records:
        modes_seen = {
            v.attack_mode
            for v in variants
            if v.base_scenario_id == record.base_scenario_id
        }
        if modes_seen != set(ATTACK_MODES_ALL):
            raise ValueError(
                f"base {record.base_scenario_id} missing attack modes: "
                f"{set(ATTACK_MODES_ALL) - modes_seen}"
            )

    index_payload = {
        "phase5_version": 1,
        "n_base_bundles": len(base_records),
        "n_attack_modes": len(ATTACK_MODES_ALL),
        "n_variants": len(variants),
        "attack_modes": list(ATTACK_MODES_ALL),
        "variants": [asdict(v) for v in variants],
    }
    (base_path / PHASE5_VARIANT_INDEX_FILENAME).write_text(
        json.dumps(index_payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return variants


def load_variant_index(index_path: Path | str) -> list[VariantRecord]:
    """Reload the variant index written by :func:`expand_base_records_to_variants`."""
    raw = json.loads(Path(index_path).read_text(encoding="utf-8"))
    return [
        VariantRecord(
            variant_id=row["variant_id"],
            base_scenario_id=row["base_scenario_id"],
            cell_id=row["cell_id"],
            family_id=row["family_id"],
            task_index=row["task_index"],
            tier_index=row["tier_index"],
            attack_mode=row["attack_mode"],
            attack_intensity=row["attack_intensity"],
            attack_recipe=row.get("attack_recipe"),
            delivery_surface=row.get("delivery_surface"),
            attacker_control=row.get("attacker_control"),
            target_agent_id=row.get("target_agent_id"),
            bundle_dir=row["bundle_dir"],
            attack_metadata=dict(row.get("attack_metadata") or {}),
        )
        for row in raw["variants"]
    ]
