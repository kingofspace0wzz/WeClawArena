"""Per-provider token rate table + cost estimation helper.

Phase G4. The batch runner (:mod:`scripts.run_grid`) uses this module to
convert raw token counts into an ``estimated_cost_usd`` column in
``cost.csv``. Rates are loaded lazily from a YAML file at
``clawsocialarena/experiments/rates.yaml`` so pricing stays editable
without touching Python.

Each rate entry carries ``input``, ``output``, and ``cached_input``
rates in USD per 1,000,000 tokens — the unit every provider bills in.
Missing entries fall back to a zero rate so unknown models do not
crash the runner; the cost column will be zero, which is the correct
default for a model without pricing data (mock models, dry runs, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml


_RATES_YAML = Path(__file__).with_name("rates.yaml")


@dataclass(frozen=True)
class RateEntry:
    """Per-model USD rate schedule.

    Attributes:
        input_usd_per_m: USD charged per 1,000,000 input (prompt) tokens.
        output_usd_per_m: USD charged per 1,000,000 output (completion) tokens.
        cached_input_usd_per_m: USD charged per 1,000,000 cached-prompt
            tokens. Providers that support prompt caching (Anthropic's
            ``cache_control``, OpenAI's prompt caching, etc.) bill these
            at a steep discount relative to fresh input tokens.
    """

    input_usd_per_m: float
    output_usd_per_m: float
    cached_input_usd_per_m: float


@lru_cache(maxsize=1)
def _load_rates() -> dict[str, RateEntry]:
    """Parse ``rates.yaml`` once per process and cache the result."""

    if not _RATES_YAML.exists():
        return {}
    raw = yaml.safe_load(_RATES_YAML.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(
            f"rates.yaml must be a mapping, got {type(raw).__name__}"
        )
    entries: dict[str, RateEntry] = {}
    for model, fields in raw.items():
        if not isinstance(fields, dict):
            raise ValueError(
                f"rates.yaml entry for {model!r} must be a mapping"
            )
        entries[str(model)] = RateEntry(
            input_usd_per_m=float(fields.get("input_usd_per_m", 0.0)),
            output_usd_per_m=float(fields.get("output_usd_per_m", 0.0)),
            cached_input_usd_per_m=float(
                fields.get("cached_input_usd_per_m", 0.0)
            ),
        )
    return entries


def get_rate(model: str) -> RateEntry:
    """Return the rate entry for ``model`` or a zero-rate fallback."""

    entries = _load_rates()
    return entries.get(model, RateEntry(0.0, 0.0, 0.0))


def estimate_cost_usd(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
) -> float:
    """Return the estimated USD cost for a single run.

    Cached tokens are counted against the cached-input rate and are NOT
    double-counted against ``input_tokens``. Callers should pass the
    fresh-input token count (total input minus cached) via
    ``input_tokens`` and the cached count via ``cached_tokens``. The
    gateway's ``LLM_CALL`` action layout already splits the two fields.
    """

    rate = get_rate(model)
    input_cost = (input_tokens / 1_000_000) * rate.input_usd_per_m
    output_cost = (output_tokens / 1_000_000) * rate.output_usd_per_m
    cached_cost = (cached_tokens / 1_000_000) * rate.cached_input_usd_per_m
    return input_cost + output_cost + cached_cost
