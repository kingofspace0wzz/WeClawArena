from clawsocialarena.baselines.prompt_ladder import (
    PrivacyLevel,
    level_prefix,
    system_prompt_with_level,
)


def test_l0_is_empty_prefix():
    assert level_prefix(PrivacyLevel.L0) == ""


def test_levels_produce_distinct_prefixes():
    seen = {level_prefix(l) for l in PrivacyLevel}
    assert len(seen) == len(PrivacyLevel)


def test_prompt_prepended():
    base = "You are Alice's agent."
    prompt = system_prompt_with_level(base, PrivacyLevel.L3)
    assert prompt.startswith(base)
    assert "Minimum Necessary" in prompt


def test_ordinal_ordering():
    # IntEnum ordering is structural
    assert PrivacyLevel.L0 < PrivacyLevel.L1 < PrivacyLevel.L4
