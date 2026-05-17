"""Tests for the Phase-5 per-family task-variant table (S3 step 2).

The variants table is the only authority on identity variation across
the pilot's 126 base bundles. Drift here would cause cells that share
a family to converge on the same base scenario, defeating the point
of the variant axis. These tests pin the contract.
"""
from __future__ import annotations

import pytest

from clawsocialarena.generator.family_pack_registry import (
    FAMILY_LOADERS,
    load_and_materialize,
)
from clawsocialarena.generator.phase5_task_variants import (
    TaskVariantSpec,
    task_variant_at,
    task_variants_for,
)


_EXPECTED_VARIANT_COUNTS: dict[str, int] = {
    "marble_research": 8,
    "marble_bargaining": 3,
    "tau2_retail": 3,
    "tau2_airline": 3,
    "tau2_telecom": 3,
    "travel": 6,
    "wildclaw_social": 3,
}


def test_every_registered_family_has_expected_variant_count() -> None:
    for family_id in FAMILY_LOADERS:
        variants = task_variants_for(family_id)
        expected = _EXPECTED_VARIANT_COUNTS.get(family_id, 3)
        assert len(variants) == expected, (
            f"{family_id} has {len(variants)} variants; expected {expected}"
        )
        assert [v.task_index for v in variants] == list(range(expected))


def test_variants_are_distinct_within_a_family() -> None:
    """Identity kwargs must differ across all variants so the
    materialized bundles are not duplicates.
    """
    for family_id in FAMILY_LOADERS:
        variants = task_variants_for(family_id)
        n = len(variants)
        labels = {v.label for v in variants}
        assert len(labels) == n, f"{family_id} variants share labels: {labels}"
        scenario_ids = {v.loader_kwargs["scenario_id"] for v in variants}
        assert len(scenario_ids) == n, (
            f"{family_id} variants share scenario_ids: {scenario_ids}"
        )


def test_variants_use_disjoint_participant_owners() -> None:
    """Variants must not share participant owner names where owner-keyed
    per-variant paths are used for materialization.

    marble_research is exempt from this check because its redesign
    intentionally shares PI owners across tasks within a seed (e.g.,
    owner 'alpha' appears in tasks 1.1, 1.2, and 1.3). The per-PI
    SQLite is written once per seed and shared; paths are keyed by
    seed + task index, not by owner alone.
    """
    _OWNER_SHARING_EXEMPT = {"marble_research"}
    for family_id in FAMILY_LOADERS:
        if family_id in _OWNER_SHARING_EXEMPT:
            continue
        variants = task_variants_for(family_id)
        all_owner_sets: list[set[str]] = []
        for variant in variants:
            owner_keys = [
                k for k in variant.loader_kwargs if k.endswith("_owner")
            ]
            all_owner_sets.append(
                {variant.loader_kwargs[k] for k in owner_keys}
            )
        # Each set should be disjoint from every other for the same family.
        for i, lhs in enumerate(all_owner_sets):
            for j, rhs in enumerate(all_owner_sets):
                if i >= j:
                    continue
                assert not (lhs & rhs), (
                    f"{family_id} variants {i} and {j} share owners: "
                    f"{lhs & rhs}"
                )


def test_task_variant_at_returns_spec_or_raises() -> None:
    spec = task_variant_at("tau2_retail", 0)
    assert isinstance(spec, TaskVariantSpec)
    assert spec.task_index == 0
    with pytest.raises(IndexError):
        task_variant_at("tau2_retail", 3)
    with pytest.raises(KeyError):
        task_variants_for("not_a_real_family")


@pytest.mark.parametrize("family_id", sorted(FAMILY_LOADERS.keys()))
def test_every_variant_kwarg_set_loads_and_materializes(
    family_id: str, tmp_path
) -> None:
    """Each of the three identity kwarg sets must drive the loader
    successfully end-to-end. This catches typos in kwarg names that
    would otherwise only surface at orchestration time.
    """
    variants = task_variants_for(family_id)
    for variant in variants:
        bundle_dir, bundle = load_and_materialize(
            family_id=family_id,
            out_dir=tmp_path / family_id / variant.label,
            load_kwargs=variant.loader_kwargs,
        )
        assert bundle_dir.is_dir(), (
            f"{family_id} variant {variant.task_index} produced no bundle dir"
        )
        # Every bundle exposes the scenario by contract.
        assert bundle.scenario is not None
