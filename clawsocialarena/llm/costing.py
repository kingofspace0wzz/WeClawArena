from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ModelRate(BaseModel):
    input_per_million: float = Field(ge=0)
    cached_input_per_million: float = Field(ge=0)
    output_per_million: float = Field(ge=0)
    source_url: str
    effective_date: str


class TokenUsage(BaseModel):
    model: str
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @field_validator("model")
    @classmethod
    def _canonicalize_model(cls, value: str) -> str:
        return canonical_model_id(value)

    def add(self, other: TokenUsage) -> TokenUsage:
        if self.model != other.model:
            raise ValueError("cannot add token usage from different models")
        return TokenUsage(
            model=self.model,
            input_tokens=self.input_tokens + other.input_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class CostProjection(BaseModel):
    point_estimate: float
    with_25_percent_buffer: float
    with_50_percent_buffer: float


MODEL_ALIASES: dict[str, str] = {
    "gpt-5-2025-08-07": "gpt-5",
    "gpt-4.1-mini-2025-04-14": "gpt-4.1-mini",
}


def canonical_model_id(model: str) -> str:
    return MODEL_ALIASES.get(model, model)


MODEL_RATES: dict[str, ModelRate] = {
    "gpt-5": ModelRate(
        input_per_million=1.25,
        cached_input_per_million=0.125,
        output_per_million=10.0,
        source_url="https://developers.openai.com/api/docs/models/gpt-5",
        effective_date="2026-05-02",
    ),
    "gpt-5.2": ModelRate(
        input_per_million=1.75,
        cached_input_per_million=0.175,
        output_per_million=14.0,
        source_url="https://platform.openai.com/docs/models/gpt-5.2",
        effective_date="2026-05-06",
    ),
    "gpt-4.1-mini": ModelRate(
        input_per_million=0.40,
        cached_input_per_million=0.10,
        output_per_million=1.60,
        source_url="https://developers.openai.com/api/docs/models/gpt-4.1-mini",
        effective_date="2026-05-02",
    ),
}


def estimate_cost_usd(
    usage: TokenUsage,
    *,
    rates: dict[str, ModelRate] = MODEL_RATES,
) -> float:
    if usage.cached_input_tokens > usage.input_tokens:
        raise ValueError("cached_input_tokens cannot exceed input_tokens")
    model = canonical_model_id(usage.model)
    if model not in rates:
        raise KeyError(f"missing rate for model {usage.model!r}")

    rate = rates[model]
    uncached_input_tokens = usage.input_tokens - usage.cached_input_tokens
    return (
        uncached_input_tokens / 1_000_000 * rate.input_per_million
        + usage.cached_input_tokens / 1_000_000 * rate.cached_input_per_million
        + usage.output_tokens / 1_000_000 * rate.output_per_million
    )


def project_full_benchmark_cost(
    *,
    batch_cost_usd: float,
    accepted_count: int,
    target_count: int = 550,
) -> CostProjection:
    if accepted_count <= 0:
        raise ValueError("accepted_count must be positive for cost projection")
    if target_count < accepted_count:
        raise ValueError("target_count cannot be smaller than accepted_count")

    cost_per_accepted = batch_cost_usd / accepted_count
    point_estimate = batch_cost_usd + (
        target_count - accepted_count
    ) * cost_per_accepted
    return CostProjection(
        point_estimate=point_estimate,
        with_25_percent_buffer=point_estimate * 1.25,
        with_50_percent_buffer=point_estimate * 1.50,
    )
