"""Tests for the Phase-5 attack-variant injector (S3 step 5).

Pins the spec section 2 matched-axis contract:
- 5 modes per base: no_attacker / collaboration / security / privacy / governance.
- Each non-baseline variant carries attack_recipe + delivery_surface +
  attacker_control + target_agent_id.
- opening-message variants rewrite opening_message.to so the attack is
  delivered to the intended recipient (codex Batch S3 regression).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawsocialarena.generator.cell_allocation import cell_by_index
from clawsocialarena.generator.family_pack_registry import FAMILY_LOADERS
from clawsocialarena.generator.phase5_attack_payloads import (
    ATTACK_MODES_ALL,
    ATTACK_MODES_NON_BASELINE,
    MODE_TO_RECIPE,
)
from clawsocialarena.generator.phase5_attack_variants import (
    PHASE5_VARIANT_INDEX_FILENAME,
    PHASE5_VARIANT_METADATA_FILENAME,
    VariantRecord,
    expand_base_records_to_variants,
    load_variant_index,
)
from clawsocialarena.generator.phase5_base_generator import (
    generate_base_bundles,
)


def test_expand_produces_five_variants_per_base(tmp_path: Path) -> None:
    cell = cell_by_index(0)
    base_records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    variants = expand_base_records_to_variants(
        base_records=base_records, base_dir=tmp_path
    )
    # 9 base bundles * 5 modes = 45 variants for one cell.
    assert len(variants) == len(base_records) * len(ATTACK_MODES_ALL)
    by_base: dict[str, set[str]] = {}
    for variant in variants:
        by_base.setdefault(variant.base_scenario_id, set()).add(
            variant.attack_mode
        )
    for base_id, modes in by_base.items():
        assert modes == set(ATTACK_MODES_ALL), (
            f"base {base_id} missing modes: "
            f"{set(ATTACK_MODES_ALL) - modes}"
        )


def test_variant_ids_use_mode_axis_label(tmp_path: Path) -> None:
    cell = cell_by_index(0)
    base_records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    variants = expand_base_records_to_variants(
        base_records=base_records, base_dir=tmp_path
    )
    ids = [v.variant_id for v in variants]
    assert len(set(ids)) == len(ids)
    for variant in variants:
        assert variant.variant_id.endswith(f"__{variant.attack_mode}")
        assert variant.variant_id.startswith(variant.base_scenario_id)


def test_non_baseline_variants_carry_recipe_and_surface(tmp_path: Path) -> None:
    cell = cell_by_index(0)
    base_records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    variants = expand_base_records_to_variants(
        base_records=base_records, base_dir=tmp_path
    )
    for variant in variants:
        if variant.attack_mode == "no_attacker":
            assert variant.attack_recipe is None
            assert variant.delivery_surface is None
            assert variant.attacker_control is None
            assert variant.target_agent_id is None
        else:
            assert variant.attack_recipe == MODE_TO_RECIPE[variant.attack_mode]
            assert variant.delivery_surface == "message"
            assert variant.attacker_control == "scripted"
            assert variant.target_agent_id, (
                f"{variant.variant_id} missing target_agent_id"
            )


def test_baseline_variant_reuses_base_bundle_dir(tmp_path: Path) -> None:
    cell = cell_by_index(0)
    base_records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    variants = expand_base_records_to_variants(
        base_records=base_records, base_dir=tmp_path
    )
    base_dirs_by_id = {r.base_scenario_id: r.bundle_dir for r in base_records}
    for variant in variants:
        if variant.attack_mode == "no_attacker":
            assert variant.bundle_dir == base_dirs_by_id[variant.base_scenario_id]


def test_attack_variants_write_separate_scenario_and_sidecar(
    tmp_path: Path,
) -> None:
    cell = cell_by_index(0)
    base_records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    variants = expand_base_records_to_variants(
        base_records=base_records, base_dir=tmp_path
    )
    for variant in variants:
        if variant.attack_mode == "no_attacker":
            continue
        variant_dir = tmp_path / variant.bundle_dir
        scenario_path = variant_dir / "scenario.json"
        sidecar_path = variant_dir / PHASE5_VARIANT_METADATA_FILENAME
        assert scenario_path.is_file(), f"missing scenario for {variant.variant_id}"
        assert sidecar_path.is_file(), f"missing sidecar for {variant.variant_id}"
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert sidecar["attack"]["attack_mode"] == variant.attack_mode
        assert sidecar["attack"]["attack_recipe"] == variant.attack_recipe


def test_attack_sidecar_carries_every_spec_section_2_field(
    tmp_path: Path,
) -> None:
    """Spec section 2 requires every adversarial variant to declare
    attack_mode + attack_recipe + attack_intensity + delivery_surface +
    attacker_control. Codex S3 re-review caught attack_intensity
    missing from the on-disk sidecar; this regression pins all five.
    """
    cell = cell_by_index(0)
    base_records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    expand_base_records_to_variants(
        base_records=base_records, base_dir=tmp_path
    )
    required = {
        "attack_mode",
        "attack_recipe",
        "attack_intensity",
        "delivery_surface",
        "attacker_control",
    }
    # Reload via the on-disk sidecars rather than via VariantRecord to
    # confirm the persisted artifact is correct, not just the in-memory
    # row.
    for record in base_records:
        bundle_dir = tmp_path / record.bundle_dir
        attack_dir = bundle_dir / "attack_variants"
        for mode_dir in attack_dir.iterdir():
            sidecar = json.loads(
                (mode_dir / PHASE5_VARIANT_METADATA_FILENAME)
                .read_text(encoding="utf-8")
            )
            missing = required - set(sidecar["attack"].keys())
            assert not missing, (
                f"{record.base_scenario_id}/{mode_dir.name}: "
                f"sidecar missing spec section 2 fields: {missing}"
            )
            # attack_intensity must agree with the base record's tier.
            assert sidecar["attack"]["attack_intensity"] == record.attack_intensity


def test_attack_variant_scenario_carries_payload_text(tmp_path: Path) -> None:
    cell = cell_by_index(0)
    base_records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    variants = expand_base_records_to_variants(
        base_records=base_records, base_dir=tmp_path
    )
    for variant in variants:
        if variant.attack_mode == "no_attacker":
            continue
        scenario_path = tmp_path / variant.bundle_dir / "scenario.json"
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        sidecar = json.loads(
            (tmp_path / variant.bundle_dir / PHASE5_VARIANT_METADATA_FILENAME)
            .read_text(encoding="utf-8")
        )
        payload_text = sidecar["attack"]["payload_text"]
        opening = scenario.get("opening_message") or {}
        injected = scenario.get("injected_messages") or []
        haystack = opening.get("content", "") + "".join(
            m.get("content", "") for m in injected
        )
        assert payload_text in haystack, (
            f"variant {variant.variant_id} scenario does not contain its payload"
        )


def test_opening_message_attack_retargets_recipient(tmp_path: Path) -> None:
    """Codex Batch S3 regression: when the payload's message_kind is
    ``opening_message``, the injected scenario's ``opening_message.to``
    must be rewritten to the payload's ``target_agent_id``. Otherwise
    the attack lands on the wrong agent in tau2_retail / tau2_telecom
    where the base opening_message is addressed to the secondary.
    """
    from clawsocialarena.generator.cell_allocation import all_cells

    for family_id in ("tau2_retail", "tau2_telecom"):
        cell = next(c for c in all_cells() if c.family_id == family_id)
        per_family_dir = tmp_path / family_id
        base_records = generate_base_bundles(
            out_dir=per_family_dir, cells=(cell,)
        )
        variants = expand_base_records_to_variants(
            base_records=base_records, base_dir=per_family_dir
        )
        for variant in variants:
            if variant.attack_mode == "no_attacker":
                continue
            scenario = json.loads(
                (per_family_dir / variant.bundle_dir / "scenario.json")
                .read_text(encoding="utf-8")
            )
            sidecar = json.loads(
                (
                    per_family_dir
                    / variant.bundle_dir
                    / PHASE5_VARIANT_METADATA_FILENAME
                ).read_text(encoding="utf-8")
            )
            if sidecar["attack"]["message_kind"] != "opening_message":
                continue
            target = sidecar["attack"]["target_agent_id"]
            opening_to = scenario["opening_message"]["to"]
            assert opening_to == target, (
                f"{family_id} {variant.attack_mode}: opening_message.to="
                f"{opening_to!r} but target_agent_id={target!r}"
            )


def test_variant_index_round_trips(tmp_path: Path) -> None:
    cell = cell_by_index(0)
    base_records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    expand_base_records_to_variants(
        base_records=base_records, base_dir=tmp_path
    )
    index_path = tmp_path / PHASE5_VARIANT_INDEX_FILENAME
    assert index_path.is_file()
    reloaded = load_variant_index(index_path)
    assert len(reloaded) == 9 * 5
    assert all(isinstance(v, VariantRecord) for v in reloaded)
    # Confirm recipe / surface / control round-trip too.
    sample = next(v for v in reloaded if v.attack_mode == "privacy")
    assert sample.attack_recipe == MODE_TO_RECIPE["privacy"]
    assert sample.delivery_surface == "message"
    assert sample.attacker_control == "scripted"


@pytest.mark.parametrize("family_id", sorted(FAMILY_LOADERS.keys()))
def test_expand_works_for_one_cell_per_family(
    family_id: str, tmp_path: Path
) -> None:
    from clawsocialarena.generator.cell_allocation import all_cells

    cell = next(c for c in all_cells() if c.family_id == family_id)
    base_records = generate_base_bundles(out_dir=tmp_path, cells=(cell,))
    variants = expand_base_records_to_variants(
        base_records=base_records, base_dir=tmp_path
    )
    assert len(variants) == 9 * 5
