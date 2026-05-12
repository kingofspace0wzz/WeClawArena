"""Tests for the Phase-5 family-pack skeleton builder (S2)."""
from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.generator.family_pack_registry import (
    FAMILY_LOADERS,
    load_and_materialize,
)
from clawsocialarena.generator.family_pack_skeleton import (
    FamilyPackSkeleton,
    build_family_pack_skeleton,
)


@pytest.fixture
def materialized_bundle(tmp_path: Path):
    bundle_dir, bundle = load_and_materialize(
        family_id="tau2_retail", out_dir=tmp_path / "retail"
    )
    return bundle_dir, bundle


def test_skeleton_payload_carries_family_pack_block(
    materialized_bundle,
) -> None:
    bundle_dir, _bundle = materialized_bundle
    skeleton = build_family_pack_skeleton(
        family_id="tau2_retail", bundle_dir=bundle_dir
    )
    assert isinstance(skeleton, FamilyPackSkeleton)
    family_pack = skeleton.payload["family_pack"]
    assert family_pack["family_id"] == "tau2_retail"
    assert isinstance(family_pack["context"], dict)
    hints = family_pack["hints"]
    assert "domain" in hints
    assert "naturalization_focus" in hints
    assert "key_terms" in hints


def test_skeleton_includes_evaluation_criteria_instead_of_terminal_predicate(
    materialized_bundle,
) -> None:
    bundle_dir, _bundle = materialized_bundle
    skeleton = build_family_pack_skeleton(
        family_id="tau2_retail", bundle_dir=bundle_dir
    )
    assert "evaluation_criteria" in skeleton.payload
    eval_block = skeleton.payload["evaluation_criteria"]
    assert isinstance(eval_block, dict)
    assert "env_assertions" in eval_block


def test_skeleton_includes_scenario_and_resource_manifest(
    materialized_bundle,
) -> None:
    bundle_dir, _bundle = materialized_bundle
    skeleton = build_family_pack_skeleton(
        family_id="tau2_retail", bundle_dir=bundle_dir
    )
    assert skeleton.payload["scenario"]["family_id"] == "tau2_retail"
    assert isinstance(skeleton.payload["resource_manifest"], dict)


def test_skeleton_unknown_family_id_raises(tmp_path: Path) -> None:
    with pytest.raises(KeyError) as excinfo:
        build_family_pack_skeleton(
            family_id="does_not_exist", bundle_dir=tmp_path
        )
    # Error must list registered ids so a typo is easy to fix.
    for fid in FAMILY_LOADERS:
        assert fid in str(excinfo.value)


def test_skeleton_index_row_is_threaded_through(materialized_bundle) -> None:
    bundle_dir, _bundle = materialized_bundle
    row = {"scenario_id": "PHASE5-0001", "cell_id": "CD-A-marble_research"}
    skeleton = build_family_pack_skeleton(
        family_id="tau2_retail", bundle_dir=bundle_dir, index_row=row
    )
    assert skeleton.payload["index_row"] == row


@pytest.mark.parametrize("family_id", sorted(FAMILY_LOADERS.keys()))
def test_skeleton_builds_for_every_pack(family_id: str, tmp_path: Path) -> None:
    bundle_dir, _bundle = load_and_materialize(
        family_id=family_id, out_dir=tmp_path / family_id
    )
    skeleton = build_family_pack_skeleton(
        family_id=family_id,
        bundle_dir=bundle_dir,
        cell_id=f"{family_id}-cell",
    )
    assert skeleton.family_id == family_id
    assert skeleton.cell_id == f"{family_id}-cell"
    # Every skeleton must carry the family-pack block and an evaluation_criteria.
    assert "family_pack" in skeleton.payload
    assert "evaluation_criteria" in skeleton.payload
    assert skeleton.payload["family_pack"]["hints"], (
        f"{family_id} skeleton has empty hints"
    )


def test_resource_payloads_include_family_pack_context(
    materialized_bundle,
) -> None:
    bundle_dir, _bundle = materialized_bundle
    skeleton = build_family_pack_skeleton(
        family_id="tau2_retail", bundle_dir=bundle_dir
    )
    payloads = skeleton.payload["resource_payloads"]
    # tau2_retail's resources/ directory ships orders.json under household/.
    # Confirm at least one JSON artifact was captured.
    assert payloads, "resource_payloads is empty"
    # Every captured key is a relative path string and every value is a dict / list.
    for rel_path, payload in payloads.items():
        assert isinstance(rel_path, str)
        assert isinstance(payload, (dict, list))
