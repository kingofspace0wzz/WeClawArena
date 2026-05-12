"""Tests for the legacy difficulty-tier shims.

Difficulty tiers were retired in v2 (spec
2026-05-12-persisted-naturalized-scenarios-design.md). The functions
in :mod:`clawsocialarena.generator.difficulty_tier` still exist for
import-path stability but always return the tier-1 ("easy") profile
regardless of the ``tier_index`` arg. These tests pin that legacy
behavior.
"""
from __future__ import annotations

import copy

from clawsocialarena.generator.difficulty_tier import (
    PER_PACK_TIER_OVERRIDES,
    TIERS,
    TierApplyResult,
    TierSpec,
    apply_tier,
    tier_for,
)
from clawsocialarena.generator.family_pack_registry import FAMILY_LOADERS


def test_tiers_table_still_lists_three_named_tiers() -> None:
    """The TIERS table is preserved for legacy callers that read tier
    metadata directly; ordering and names are unchanged from the
    pre-retirement spec.
    """
    multipliers = [t.max_turns_multiplier for t in TIERS]
    intensities = [t.attack_intensity for t in TIERS]
    assert multipliers == sorted(multipliers, reverse=True), (
        "tier max_turns_multiplier must decrease across tiers; "
        f"got {multipliers}"
    )
    assert intensities == sorted(intensities), (
        f"tier attack_intensity must increase across tiers; got {intensities}"
    )
    assert {t.tier for t in TIERS} == {1, 2, 3}
    assert {t.name for t in TIERS} == {"easy", "realistic", "stress"}


def test_tier_for_always_returns_easy_regardless_of_index() -> None:
    """LEGACY: tier_for always returns the tier-1 ("easy") spec, even
    for indices that historically meant realistic / stress / invalid.
    """
    for tier_index in (1, 2, 3, 99, 0, -1):
        spec = tier_for(tier_index)
        assert isinstance(spec, TierSpec)
        assert spec.tier == 1
        assert spec.name == "easy"
    # None is also accepted now that tier_index is Optional[int].
    spec_none = tier_for(None)
    assert spec_none.tier == 1
    assert spec_none.name == "easy"


def test_apply_tier_always_uses_easy_max_turns_multiplier() -> None:
    """LEGACY: regardless of tier_index, apply_tier uses the easy
    multiplier (1.0) so max_turns is preserved unchanged.
    """
    scenario = {"max_turns": 10, "opening_message": {"content": "Hello."}}
    res_1 = apply_tier(family_id="tau2_retail", scenario_dict=scenario, tier_index=1)
    res_2 = apply_tier(family_id="tau2_retail", scenario_dict=scenario, tier_index=2)
    res_3 = apply_tier(family_id="tau2_retail", scenario_dict=scenario, tier_index=3)
    # All three results match the easy-tier behavior (multiplier 1.0).
    assert res_1.scenario_overrides["max_turns"] == 10
    assert res_2.scenario_overrides["max_turns"] == 10
    assert res_3.scenario_overrides["max_turns"] == 10


def test_apply_tier_defaults_max_turns_when_absent() -> None:
    """A scenario without max_turns should fall back to the 12-turn base
    used elsewhere in the generator; with easy semantics (multiplier
    1.0) the result is the base value unchanged.
    """
    scenario: dict = {"opening_message": {"content": ""}}
    res = apply_tier(
        family_id="tau2_retail", scenario_dict=scenario, tier_index=2
    )
    # Base 12 * 1.0 (easy multiplier) = 12.
    assert res.scenario_overrides["max_turns"] == 12


def test_apply_tier_does_not_append_opening_clause_at_any_tier() -> None:
    """LEGACY: the easy tier has an empty opening_message_clause, so no
    opening override is ever produced regardless of tier_index.
    """
    scenario = {
        "max_turns": 12,
        "opening_message": {"content": "Resolve order #W123."},
    }
    for tier_index in (1, 2, 3):
        res = apply_tier(
            family_id="tau2_retail",
            scenario_dict=scenario,
            tier_index=tier_index,
        )
        assert "opening_message" not in res.scenario_overrides


def test_apply_tier_does_not_mutate_caller_scenario() -> None:
    scenario = {
        "max_turns": 12,
        "opening_message": {"content": "Resolve order #W123."},
    }
    snapshot = copy.deepcopy(scenario)
    apply_tier(family_id="tau2_retail", scenario_dict=scenario, tier_index=3)
    assert scenario == snapshot


def test_apply_tier_returns_tier_apply_result_with_easy_attack_intensity() -> None:
    """LEGACY: even at tier_index=3, the returned attack_intensity is
    the easy tier's 0.4 because tier_for always returns TIERS[0].
    """
    res = apply_tier(
        family_id="tau2_retail",
        scenario_dict={"max_turns": 12, "opening_message": {"content": "x"}},
        tier_index=3,
    )
    assert isinstance(res, TierApplyResult)
    assert res.attack_intensity == TIERS[0].attack_intensity == 0.4
    assert res.tier.tier == 1
    assert res.tier.name == "easy"


def test_per_pack_override_dict_covers_every_registered_family() -> None:
    """Every registered pack must have an override hook (no-op or real),
    so the dispatch never falls back silently.
    """
    missing = set(FAMILY_LOADERS.keys()) - set(PER_PACK_TIER_OVERRIDES.keys())
    assert not missing, f"PER_PACK_TIER_OVERRIDES missing entries for: {missing}"


def test_marble_bargaining_override_is_inert_at_legacy_easy_tier() -> None:
    """LEGACY: the marble bargaining override only narrows the window
    for tier 2/3, but tier_for now always returns tier 1, so the
    override is inert for every tier_index input.
    """
    scenario = {
        "max_turns": 12,
        "opening_message": {"content": "Negotiate."},
        "initial_state": {"market_reference_price": 100.0},
    }
    for tier_index in (1, 2, 3):
        res = apply_tier(
            family_id="marble_bargaining",
            scenario_dict=scenario,
            tier_index=tier_index,
        )
        # No _phase_5_bargaining_window because the override returns the
        # bundle unchanged when tier.tier == 1.
        assert res.metadata.get("per_pack_extras") == {}


def test_apply_tier_with_no_opening_message_is_safe() -> None:
    """Some scenario shapes may not yet have an opening_message at tier
    time; the helper must not crash.
    """
    scenario = {"max_turns": 8}
    res = apply_tier(
        family_id="tau2_retail", scenario_dict=scenario, tier_index=3
    )
    assert "opening_message" not in res.scenario_overrides
    # Easy multiplier 1.0 preserves the original max_turns.
    assert res.scenario_overrides["max_turns"] == 8


def test_apply_tier_unknown_family_falls_back_to_no_op_override() -> None:
    """Unknown family ids must not crash apply_tier (the loader/registry
    layers are the ones that reject unknown ids); we only ensure the
    override lookup defaults to no-op so the legacy easy-tier scaling
    still works for ad-hoc family ids.
    """
    res = apply_tier(
        family_id="not_a_real_pack",
        scenario_dict={"max_turns": 10, "opening_message": {"content": "x"}},
        tier_index=2,
    )
    # Easy multiplier 1.0 -> 10 unchanged.
    assert res.scenario_overrides["max_turns"] == 10
    assert res.metadata["per_pack_extras"] == {}
