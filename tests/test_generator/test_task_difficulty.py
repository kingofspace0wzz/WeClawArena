"""Tests for the legacy ``difficulty_profile`` shim.

Difficulty tiers were retired in v2 (spec
2026-05-12-persisted-naturalized-scenarios-design.md).
:func:`clawsocialarena.generator.task_difficulty.difficulty_profile`
still exists for import-path stability but always returns the "easy"
profile regardless of the ``tier`` arg. These tests pin that legacy
behavior.
"""
from clawsocialarena.generator.task_difficulty import difficulty_profile


def test_scheduling_profile_always_returns_easy_regardless_of_tier() -> None:
    """LEGACY: tier="stress" no longer returns the stress profile;
    the easy profile is returned for every tier input.
    """
    for tier in ("easy", "realistic", "stress", None):
        profile = difficulty_profile(family="scheduling", tier=tier)
        assert profile["designed_difficulty_tier"] == "easy"
        # Easy scheduling profile uses 30-minute duration and the
        # mutually-available wording.
        assert profile["terminal_patch"]["duration_minutes"] == 30
        assert "mutually available" in profile["opening_suffix"].lower()
        assert "hard_constraints" not in profile["terminal_patch"]


def test_scheduling_easy_profile_uses_reader_facing_wording() -> None:
    profile = difficulty_profile(family="scheduling", tier="easy")

    assert "single explicit availability window" not in profile["opening_suffix"].lower()
    assert "mutually available" in profile["opening_suffix"].lower()


def test_inference_profile_always_returns_easy_regardless_of_tier() -> None:
    """LEGACY: tier="realistic" no longer returns the realistic
    profile; the easy profile is returned for every tier input.
    """
    for tier in ("easy", "realistic", "stress", None):
        profile = difficulty_profile(family="inference", tier=tier)
        assert profile["designed_difficulty_tier"] == "easy"
        # Easy inference profile requires only "next step".
        assert profile["task_success_predicate"]["required_terms"] == ["next step"]
        assert "next step" in profile["system_prompt_suffix"].lower()


def test_inference_easy_profile_prompts_required_next_step() -> None:
    profile = difficulty_profile(family="inference", tier="easy")

    assert profile["task_success_predicate"]["required_terms"] == ["next step"]
    assert "next step" in profile["system_prompt_suffix"].lower()


def test_hard_family_profiles_collapse_to_easy_in_legacy_mode() -> None:
    """LEGACY: code_review and doc_editing easy / stress no longer
    differ; both tiers collapse to the easy profile.
    """
    code_easy = difficulty_profile(family="code_review", tier="easy")
    code_stress = difficulty_profile(family="code_review", tier="stress")
    doc_easy = difficulty_profile(family="doc_editing", tier="easy")
    doc_stress = difficulty_profile(family="doc_editing", tier="stress")

    assert code_easy["terminal_patch"] == code_stress["terminal_patch"]
    assert code_easy["source_pattern"]["path"] == code_stress["source_pattern"]["path"]
    assert doc_easy["terminal_patch"] == doc_stress["terminal_patch"]
    assert doc_easy["source_pattern"]["path"] == doc_stress["source_pattern"]["path"]
    # All four carry the easy designation.
    for profile in (code_easy, code_stress, doc_easy, doc_stress):
        assert profile["designed_difficulty_tier"] == "easy"
