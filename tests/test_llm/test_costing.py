import pytest

from clawsocialarena.llm.costing import (
    MODEL_RATES,
    TokenUsage,
    estimate_cost_usd,
    project_full_benchmark_cost,
)


def test_estimate_cost_uses_cached_token_discount() -> None:
    usage = TokenUsage(
        model="gpt-5",
        input_tokens=1_000_000,
        cached_input_tokens=250_000,
        output_tokens=100_000,
    )

    cost = estimate_cost_usd(usage, rates=MODEL_RATES)

    assert cost == pytest.approx(1.96875)


def test_token_usage_canonicalizes_dated_model_aliases() -> None:
    usage = TokenUsage(
        model="gpt-5-2025-08-07",
        input_tokens=1_000_000,
        cached_input_tokens=250_000,
        output_tokens=100_000,
    )

    assert usage.model == "gpt-5"
    assert estimate_cost_usd(usage, rates=MODEL_RATES) == pytest.approx(1.96875)


def test_estimate_cost_rejects_cached_tokens_above_input_tokens() -> None:
    usage = TokenUsage(
        model="gpt-5",
        input_tokens=10,
        cached_input_tokens=11,
        output_tokens=0,
    )

    with pytest.raises(ValueError, match="cached_input_tokens"):
        estimate_cost_usd(usage, rates=MODEL_RATES)


def test_project_full_benchmark_cost_from_first_batch() -> None:
    projection = project_full_benchmark_cost(
        batch_cost_usd=12.0,
        accepted_count=8,
        target_count=550,
    )

    assert projection.point_estimate == pytest.approx(825.0)
    assert projection.with_25_percent_buffer == pytest.approx(1031.25)
    assert projection.with_50_percent_buffer == pytest.approx(1237.5)
