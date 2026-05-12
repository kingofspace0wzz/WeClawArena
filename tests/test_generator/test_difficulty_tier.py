"""Tests for the Phase-5 difficulty-tier scaffolding (S3 step 1).

These cover the three contracts the rest of S3 relies on:

- :func:`tier_for` returns the correct ``TierSpec`` and rejects bad indices.
- :func:`apply_tier` scales ``max_turns``, augments the opening message,
  and never mutates the caller's scenario dict.
- :data:`PER_PACK_TIER_OVERRIDES` covers every registered family pack
  and the marble-bargaining override narrows the window at tiers 2/3.
"""
from __future__ import annotations

import copy

import pytest

from clawsocialarena.generator.difficulty_tier import (
    PER_PACK_TIER_OVERRIDES,
    TIERS,
    TierApplyResult,
    TierSpec,
    apply_tier,
    tier_for,
)
from clawsocialarena.generator.family_pack_registry import FAMILY_LOADERS


def test_tiers_are_strictly_ordered_by_multiplier_and_intensity() -> None:
    """The tier table is the only authority on tier ordering; if anyone
    edits TIERS the multiplier must stay strictly DECREASING (higher
    tier = tighter turn budget = harder) and intensity must stay
    INCREASING (higher tier = stronger attack pressure). The spec
    section 5 designed-difficulty contract relies on this.
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
    # Spec section 5 names: easy / realistic / stress.
    assert {t.name for t in TIERS} == {"easy", "realistic", "stress"}


def test_tier_for_returns_matching_spec() -> None:
    for tier_index in (1, 2, 3):
        spec = tier_for(tier_index)
        assert isinstance(spec, TierSpec)
        assert spec.tier == tier_index


def test_tier_for_rejects_unknown_index() -> None:
    with pytest.raises(ValueError) as excinfo:
        tier_for(99)
    assert "99" in str(excinfo.value)


def test_apply_tier_scales_max_turns() -> None:
    """Higher tier = tighter (lower) max_turns. 10*1.0=10, 10*0.8=8, 10*0.6=6."""
    scenario = {"max_turns": 10, "opening_message": {"content": "Hello."}}
    res_1 = apply_tier(family_id="tau2_retail", scenario_dict=scenario, tier_index=1)
    res_2 = apply_tier(family_id="tau2_retail", scenario_dict=scenario, tier_index=2)
    res_3 = apply_tier(family_id="tau2_retail", scenario_dict=scenario, tier_index=3)
    assert res_1.scenario_overrides["max_turns"] == 10
    assert res_2.scenario_overrides["max_turns"] == 8
    assert res_3.scenario_overrides["max_turns"] == 6
    # Higher tier must be strictly tighter than lower tier.
    assert (
        res_3.scenario_overrides["max_turns"]
        < res_2.scenario_overrides["max_turns"]
        < res_1.scenario_overrides["max_turns"]
    )


def test_apply_tier_defaults_max_turns_when_absent() -> None:
    """A scenario without max_turns should fall back to the 12-turn base
    used elsewhere in the generator; tier 2 narrows that to 10 (12*0.8).
    """
    scenario: dict = {"opening_message": {"content": ""}}
    res = apply_tier(
        family_id="tau2_retail", scenario_dict=scenario, tier_index=2
    )
    # base 12 * 0.8 = 9.6 -> 10
    assert res.scenario_overrides["max_turns"] == 10


def test_apply_tier_appends_opening_clause_for_tiers_2_and_3() -> None:
    scenario = {
        "max_turns": 12,
        "opening_message": {"content": "Resolve order #W123."},
    }
    res_easy = apply_tier(
        family_id="tau2_retail", scenario_dict=scenario, tier_index=1
    )
    res_medium = apply_tier(
        family_id="tau2_retail", scenario_dict=scenario, tier_index=2
    )
    res_hard = apply_tier(
        family_id="tau2_retail", scenario_dict=scenario, tier_index=3
    )
    # Easy: no clause appended -> opening_message NOT in overrides.
    assert "opening_message" not in res_easy.scenario_overrides
    # Medium / Hard: opening message is overridden and starts with the
    # original content.
    for res in (res_medium, res_hard):
        opening = res.scenario_overrides["opening_message"]
        assert opening["content"].startswith("Resolve order #W123.")
        assert len(opening["content"]) > len("Resolve order #W123.")


def test_apply_tier_does_not_mutate_caller_scenario() -> None:
    scenario = {
        "max_turns": 12,
        "opening_message": {"content": "Resolve order #W123."},
    }
    snapshot = copy.deepcopy(scenario)
    apply_tier(family_id="tau2_retail", scenario_dict=scenario, tier_index=3)
    assert scenario == snapshot


def test_apply_tier_returns_tier_apply_result_with_attack_intensity() -> None:
    res = apply_tier(
        family_id="tau2_retail",
        scenario_dict={"max_turns": 12, "opening_message": {"content": "x"}},
        tier_index=3,
    )
    assert isinstance(res, TierApplyResult)
    assert res.attack_intensity == TIERS[2].attack_intensity == 0.8
    assert res.tier.tier == 3
    assert res.tier.name == "stress"


def test_per_pack_override_dict_covers_every_registered_family() -> None:
    """Every registered pack must have an override hook (no-op or real),
    so the dispatch never falls back silently.
    """
    missing = set(FAMILY_LOADERS.keys()) - set(PER_PACK_TIER_OVERRIDES.keys())
    assert not missing, f"PER_PACK_TIER_OVERRIDES missing entries for: {missing}"


def test_marble_bargaining_override_narrows_window_per_tier() -> None:
    scenario = {
        "max_turns": 12,
        "opening_message": {"content": "Negotiate."},
        "initial_state": {"market_reference_price": 100.0},
    }
    res_easy = apply_tier(
        family_id="marble_bargaining", scenario_dict=scenario, tier_index=1
    )
    res_medium = apply_tier(
        family_id="marble_bargaining", scenario_dict=scenario, tier_index=2
    )
    res_hard = apply_tier(
        family_id="marble_bargaining", scenario_dict=scenario, tier_index=3
    )

    # Easy: no override -> no _phase_5_bargaining_window in metadata.
    assert res_easy.metadata.get("per_pack_extras") == {}

    medium = res_medium.metadata["per_pack_extras"]["_phase_5_bargaining_window"]
    hard = res_hard.metadata["per_pack_extras"]["_phase_5_bargaining_window"]
    # Windows shrink as tier increases: the buyer ceiling drops and the
    # seller reservation rises toward the market reference.
    assert medium["buyer_budget_ceiling"] > hard["buyer_budget_ceiling"]
    assert medium["seller_reservation"] < hard["seller_reservation"]
    # Both still bracket the market reference.
    for window in (medium, hard):
        assert window["seller_reservation"] < window["market_reference_price"]
        assert window["market_reference_price"] < window["buyer_budget_ceiling"]


def test_apply_tier_with_no_opening_message_is_safe() -> None:
    """Some scenario shapes may not yet have an opening_message at tier
    time; the helper must not crash.
    """
    scenario = {"max_turns": 8}
    res = apply_tier(
        family_id="tau2_retail", scenario_dict=scenario, tier_index=3
    )
    assert "opening_message" not in res.scenario_overrides
    assert res.scenario_overrides["max_turns"] == int(round(8 * 0.6))


def test_apply_tier_unknown_family_falls_back_to_no_op_override() -> None:
    """Unknown family ids must not crash apply_tier (the loader/registry
    layers are the ones that reject unknown ids); we only ensure the
    override lookup defaults to no-op so the base tier scaling still
    works for ad-hoc family ids during local experiments.
    """
    res = apply_tier(
        family_id="not_a_real_pack",
        scenario_dict={"max_turns": 10, "opening_message": {"content": "x"}},
        tier_index=2,
    )
    # 10 * 0.8 = 8.
    assert res.scenario_overrides["max_turns"] == 8
    assert res.metadata["per_pack_extras"] == {}
