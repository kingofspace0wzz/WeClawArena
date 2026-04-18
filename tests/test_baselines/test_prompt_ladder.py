from clawsocialarena.baselines.prompt_ladder import (
    PrivacyLevel,
    apply_ladder_to_prompts,
    level_prefix,
    scenario_variation_bundle,
    system_prompt_with_level,
)


def test_l0_is_empty_prefix():
    assert level_prefix(PrivacyLevel.L0) == ""


def test_levels_produce_distinct_prefixes():
    seen = {level_prefix(lvl) for lvl in PrivacyLevel}
    assert len(seen) == len(PrivacyLevel)


def test_prompt_prepended():
    base = "You are Alice's agent."
    prompt = system_prompt_with_level(base, PrivacyLevel.L3)
    assert prompt.startswith(base)
    assert "Minimum Necessary" in prompt


def test_ordinal_ordering():
    # IntEnum ordering is structural
    assert PrivacyLevel.L0 < PrivacyLevel.L1 < PrivacyLevel.L4


def test_apply_ladder_preserves_base_and_appends_level_prefix():
    prompts = {"A": "base-A", "B": "base-B"}
    result = apply_ladder_to_prompts(prompts, PrivacyLevel.L4)
    # Original is untouched; a new dict is returned.
    assert prompts == {"A": "base-A", "B": "base-B"}
    assert result["A"].startswith("base-A")
    assert "Zero-Disclosure-by-Default" in result["A"]
    assert result["B"].startswith("base-B")
    assert "Zero-Disclosure-by-Default" in result["B"]


def test_apply_ladder_l0_returns_unchanged_prompts():
    prompts = {"A": "base-A"}
    result = apply_ladder_to_prompts(prompts, PrivacyLevel.L0)
    assert result == prompts


def test_scenario_variation_bundle_uses_apply_ladder():
    base = {"A": "persona-A"}
    out = scenario_variation_bundle(base_prompts=base, level=PrivacyLevel.L2)
    assert out["A"].startswith("persona-A")
    assert "health" in out["A"].lower()


def test_apply_ladder_handles_empty_mapping():
    assert apply_ladder_to_prompts({}, PrivacyLevel.L4) == {}
