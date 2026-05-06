# LLM Naturalization Batch Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 10-scenario batch pipeline that naturalizes benchmark scenarios with GPT-5, runs real simulations with GPT-4.1 mini agents, evaluates outputs, and reports exact first-batch token/cost totals before scaling.

**Architecture:** Add a batch orchestrator around the existing world-pack materializer, gateway logs, Docker compose runner, and offline evaluator. Keep paid OpenAI calls behind explicit CLI flags, cost caps, and cache keys. The first batch always stops for user review after writing a token and cost report.

**Tech Stack:** Python 3.11, OpenAI Python SDK, Pydantic, pytest, Docker compose, existing `validate_bundle`, existing `EvalRunner`, existing gateway `llm_call` token logs.

## Correction as of 2026-05-05

This plan still describes the correct batch shape: GPT-5 naturalizes a small batch, GPT-4.1 mini agents run the real simulation, and the pipeline reports exact token and cost totals before scale-out. The target counts have changed. The 550-variant tree is now a pre-calibration scaffold, not the final target. The next target is the 680-variant balanced difficulty pilot, and a later release grid may expand to 1100 total variants if the pilot validates the designed difficulty tiers.

Before any paid naturalization batch, each base task must already have task schema v0 fields: actors, visibility, initialization, consensus or role rules, required evidence, evaluator bases, audit events, designed difficulty tier, task-success spec, and `source_pattern` metadata. GPT-5 can naturalize names, artifacts, and social details, but it must not change the matched-block identity, schema fields, or attack-mode comparability.

The corrected replacement gates should use the following scaffold slices:

| Gate | Index window | Variants | Base tasks | Category and family cells | Designed difficulty mix | Attack-mode mix |
|---|---:|---:|---:|---|---|---|
| `start-index 0`, `batch-size 25` | 0-24 | 25 | 5 | Cross-User agent-to-agent Scheduling: 25 variants / 5 bases | easy: 15; realistic: 10 | 5 per mode |
| `start-index 25`, `batch-size 50` | 25-74 | 50 | 10 | Cross-User agent-to-agent Scheduling: 20 variants / 4 bases; Mediated Communication Scheduling: 30 variants / 6 bases | easy: 15; realistic: 20; stress: 15 | 10 per mode |
| `start-index 75`, `batch-size 50` | 75-124 | 50 | 10 | Affinity-Modulated Scheduling: 35 variants / 7 bases; Mediated Communication Scheduling: 15 variants / 3 bases | easy: 15; realistic: 15; stress: 20 | 10 per mode |

---

## File Structure

- Create `clawsocialarena/llm/__init__.py` for LLM helper exports.
- Create `clawsocialarena/llm/costing.py` for model rates, token usage records, cost formulas, and cost projections.
- Create `clawsocialarena/llm/openai_client.py` for the minimal OpenAI Responses API client wrapper used by naturalization and runtime agents.
- Create `clawsocialarena/generator/naturalization.py` for GPT-5 naturalization request/response schemas, cache keys, patch validation, and repair prompts.
- Create `clawsocialarena/simulation/__init__.py` for simulation helper exports.
- Create `clawsocialarena/simulation/batch_runner.py` for running one accepted naturalized bundle through Docker/gateway/eval.
- Create `scripts/naturalize_and_run_batch.py` for the batch CLI.
- Create `tests/test_llm/test_costing.py`.
- Create `tests/test_generator/test_naturalization.py`.
- Create `tests/test_simulation/test_batch_runner.py`.
- Create `tests/test_scripts/test_naturalize_and_run_batch.py`.
- Modify `README.md` to document the first-batch checkpoint.
- Modify `scripts/orchestrate_benchmark.py` only if needed to consume accepted LLM-naturalized batch outputs later.

## Task 1: Add Cost Accounting Primitives

**Files:**
- Create: `clawsocialarena/llm/__init__.py`
- Create: `clawsocialarena/llm/costing.py`
- Test: `tests/test_llm/test_costing.py`

- [ ] **Step 1: Write the failing cost tests**

Create `tests/test_llm/test_costing.py`:

```python
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
        target_count=680,
    )

    assert projection.point_estimate == pytest.approx(1020.0)
    assert projection.with_25_percent_buffer == pytest.approx(1275.0)
    assert projection.with_50_percent_buffer == pytest.approx(1530.0)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_llm/test_costing.py -q
```

Expected: fails because `clawsocialarena.llm.costing` does not exist.

- [ ] **Step 3: Implement cost primitives**

Create `clawsocialarena/llm/__init__.py`:

```python
"""LLM integration helpers for benchmark construction and simulation."""
```

Create `clawsocialarena/llm/costing.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRate:
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float
    source_url: str
    effective_date: str


@dataclass(frozen=True)
class TokenUsage:
    model: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        if self.model != other.model:
            raise ValueError("cannot add token usage from different models")
        return TokenUsage(
            model=self.model,
            input_tokens=self.input_tokens + other.input_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


@dataclass(frozen=True)
class CostProjection:
    point_estimate: float
    with_25_percent_buffer: float
    with_50_percent_buffer: float


MODEL_RATES: dict[str, ModelRate] = {
    "gpt-5": ModelRate(
        input_per_million=1.25,
        cached_input_per_million=0.125,
        output_per_million=10.0,
        source_url="https://developers.openai.com/api/docs/models/gpt-5",
        effective_date="2026-05-02",
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
    if usage.model not in rates:
        raise KeyError(f"missing rate for model {usage.model!r}")
    rate = rates[usage.model]
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
    target_count: int = 680,
) -> CostProjection:
    if accepted_count <= 0:
        raise ValueError("accepted_count must be positive for cost projection")
    cost_per_accepted = batch_cost_usd / accepted_count
    point_estimate = batch_cost_usd + (target_count - accepted_count) * cost_per_accepted
    return CostProjection(
        point_estimate=point_estimate,
        with_25_percent_buffer=point_estimate * 1.25,
        with_50_percent_buffer=point_estimate * 1.50,
    )
```

- [ ] **Step 4: Run cost tests and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_llm/test_costing.py -q
```

Expected: all tests pass.

## Task 2: Define Naturalization Schemas and Cache Keys

**Files:**
- Create: `clawsocialarena/generator/naturalization.py`
- Test: `tests/test_generator/test_naturalization.py`

- [ ] **Step 1: Write failing naturalization schema tests**

Create `tests/test_generator/test_naturalization.py`:

```python
import json

from clawsocialarena.generator.naturalization import (
    NaturalizationPatch,
    build_naturalization_cache_key,
)


def test_naturalization_patch_accepts_usage_and_manifest_metadata() -> None:
    patch = NaturalizationPatch.model_validate(
        {
            "scenario_id": "cu-scheduling-001",
            "world_patch": {
                "files": {
                    "file-a": {
                        "content": "Synthetic private note.",
                        "expected_final_state": "unchanged",
                    }
                },
                "databases": {},
            },
            "scenario_patch": {
                "opening_message": "Please coordinate the appointment.",
                "persona_notes": {"alice": "Use the synthetic private note."},
            },
            "construction_metadata": {
                "naturalization_mode": "llm",
                "naturalization_model": "gpt-5",
                "prompt_hash": "sha256:prompt",
                "cache_key": "sha256:cache",
            },
            "usage": {
                "model": "gpt-5",
                "input_tokens": 1000,
                "cached_input_tokens": 100,
                "output_tokens": 500,
            },
        }
    )

    assert patch.usage.model == "gpt-5"
    assert patch.construction_metadata.naturalization_model == "gpt-5"


def test_cache_key_is_stable_for_sorted_json_payloads() -> None:
    left = {"b": 2, "a": 1}
    right = json.loads('{"a": 1, "b": 2}')

    assert build_naturalization_cache_key(left) == build_naturalization_cache_key(right)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_generator/test_naturalization.py -q
```

Expected: fails because `clawsocialarena.generator.naturalization` does not exist.

- [ ] **Step 3: Implement schemas and cache key helper**

Create `clawsocialarena/generator/naturalization.py` with Pydantic models:

```python
from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field

from clawsocialarena.llm.costing import TokenUsage


class NaturalizedFilePatch(BaseModel):
    content: str = Field(min_length=1)
    expected_final_state: str = Field(min_length=1)


class NaturalizedDatabasePatch(BaseModel):
    tables: dict[str, Any] = Field(default_factory=dict)


class NaturalizedWorldPatch(BaseModel):
    files: dict[str, NaturalizedFilePatch] = Field(default_factory=dict)
    databases: dict[str, NaturalizedDatabasePatch] = Field(default_factory=dict)


class NaturalizedScenarioPatch(BaseModel):
    opening_message: str = Field(min_length=1)
    persona_notes: dict[str, str] = Field(default_factory=dict)


class NaturalizationMetadata(BaseModel):
    naturalization_mode: str = "llm"
    naturalization_model: str = Field(min_length=1)
    prompt_hash: str = Field(min_length=1)
    cache_key: str = Field(min_length=1)


class NaturalizationPatch(BaseModel):
    scenario_id: str = Field(min_length=1)
    world_patch: NaturalizedWorldPatch
    scenario_patch: NaturalizedScenarioPatch
    construction_metadata: NaturalizationMetadata
    usage: TokenUsage


def build_naturalization_cache_key(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_generator/test_naturalization.py -q
```

Expected: all tests pass.

## Task 3: Add OpenAI Client Wrapper With Dry-Run Seam

**Files:**
- Create: `clawsocialarena/llm/openai_client.py`
- Test: `tests/test_llm/test_openai_client.py`

- [ ] **Step 1: Write failing client tests**

Create `tests/test_llm/test_openai_client.py`:

```python
import pytest

from clawsocialarena.llm.openai_client import OpenAIConfig, require_openai_key


def test_require_openai_key_rejects_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        require_openai_key()


def test_openai_config_defaults_to_pinned_models() -> None:
    config = OpenAIConfig()

    assert config.construction_model == "gpt-5"
    assert config.agent_model == "gpt-4.1-mini"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_llm/test_openai_client.py -q
```

Expected: fails because the client module does not exist.

- [ ] **Step 3: Implement minimal client configuration**

Create `clawsocialarena/llm/openai_client.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OpenAIConfig:
    construction_model: str = "gpt-5"
    agent_model: str = "gpt-4.1-mini"


def require_openai_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for paid LLM batch runs")
    return key
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_llm/test_openai_client.py -q
```

Expected: all tests pass.

## Task 4: Implement Batch Report Schema

**Files:**
- Create: `clawsocialarena/simulation/__init__.py`
- Create: `clawsocialarena/simulation/batch_runner.py`
- Test: `tests/test_simulation/test_batch_runner.py`

- [ ] **Step 1: Write failing batch report tests**

Create `tests/test_simulation/test_batch_runner.py`:

```python
from clawsocialarena.llm.costing import TokenUsage
from clawsocialarena.simulation.batch_runner import (
    BatchReport,
    BatchUsage,
    build_batch_report,
)


def test_build_batch_report_projects_cost_after_first_batch() -> None:
    report = build_batch_report(
        batch_id="batch-0001",
        scenario_ids=[f"scenario-{idx:02d}" for idx in range(10)],
        accepted_scenario_ids=[f"scenario-{idx:02d}" for idx in range(8)],
        failed_scenarios=[
            {"scenario_id": "scenario-08", "status": "simulation_failed"},
            {"scenario_id": "scenario-09", "status": "naturalization_failed"},
        ],
        usage=BatchUsage(
            construction=TokenUsage(
                model="gpt-5",
                input_tokens=2_000_000,
                cached_input_tokens=500_000,
                output_tokens=400_000,
            ),
            simulation=TokenUsage(
                model="gpt-4.1-mini",
                input_tokens=3_000_000,
                cached_input_tokens=500_000,
                output_tokens=600_000,
            ),
        ),
        stop_for_review=True,
    )

    assert isinstance(report, BatchReport)
    assert report.decision == "STOP_FOR_REVIEW"
    assert report.accepted_count == 8
    assert report.projected_full_benchmark_cost_usd is not None
    assert report.usage.total_estimated_cost_usd > 0
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_simulation/test_batch_runner.py -q
```

Expected: fails because `clawsocialarena.simulation.batch_runner` does not exist.

- [ ] **Step 3: Implement batch report models**

Create `clawsocialarena/simulation/__init__.py`:

```python
"""Simulation orchestration helpers."""
```

Create `clawsocialarena/simulation/batch_runner.py`:

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from clawsocialarena.llm.costing import (
    CostProjection,
    TokenUsage,
    estimate_cost_usd,
    project_full_benchmark_cost,
)


class BatchUsage(BaseModel):
    construction: TokenUsage
    simulation: TokenUsage
    construction_estimated_cost_usd: float = 0.0
    simulation_estimated_cost_usd: float = 0.0
    total_estimated_cost_usd: float = 0.0


class BatchReport(BaseModel):
    batch_id: str
    scenario_ids: list[str]
    accepted_scenario_ids: list[str]
    failed_scenarios: list[dict[str, Any]] = Field(default_factory=list)
    accepted_count: int
    failed_count: int
    usage: BatchUsage
    observed_cost_per_accepted_scenario_usd: float | None
    projected_full_benchmark_cost_usd: CostProjection | None
    decision: str


def build_batch_report(
    *,
    batch_id: str,
    scenario_ids: list[str],
    accepted_scenario_ids: list[str],
    failed_scenarios: list[dict[str, Any]],
    usage: BatchUsage,
    stop_for_review: bool,
) -> BatchReport:
    construction_cost = estimate_cost_usd(usage.construction)
    simulation_cost = estimate_cost_usd(usage.simulation)
    total_cost = construction_cost + simulation_cost
    accepted_count = len(accepted_scenario_ids)
    projection = (
        project_full_benchmark_cost(
            batch_cost_usd=total_cost,
            accepted_count=accepted_count,
            target_count=680,
        )
        if accepted_count > 0
        else None
    )
    return BatchReport(
        batch_id=batch_id,
        scenario_ids=scenario_ids,
        accepted_scenario_ids=accepted_scenario_ids,
        failed_scenarios=failed_scenarios,
        accepted_count=accepted_count,
        failed_count=len(failed_scenarios),
        usage=BatchUsage(
            construction=usage.construction,
            simulation=usage.simulation,
            construction_estimated_cost_usd=construction_cost,
            simulation_estimated_cost_usd=simulation_cost,
            total_estimated_cost_usd=total_cost,
        ),
        observed_cost_per_accepted_scenario_usd=(
            total_cost / accepted_count if accepted_count else None
        ),
        projected_full_benchmark_cost_usd=projection,
        decision="STOP_FOR_REVIEW" if stop_for_review else "CONTINUE",
    )
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_simulation/test_batch_runner.py -q
```

Expected: all tests pass.

## Task 5: Add Batch CLI Skeleton With Hard Safety Gates

**Files:**
- Create: `scripts/naturalize_and_run_batch.py`
- Test: `tests/test_scripts/test_naturalize_and_run_batch.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_scripts/test_naturalize_and_run_batch.py`:

```python
import json
from pathlib import Path

from scripts import naturalize_and_run_batch


def test_batch_cli_dry_run_writes_zero_cost_report(tmp_path: Path) -> None:
    out = tmp_path / "batches"

    rc = naturalize_and_run_batch.main(
        [
            "--dry-run",
            "--batch-id",
            "batch-0001",
            "--batch-size",
            "10",
            "--out",
            str(out),
        ]
    )

    assert rc == 0
    report = json.loads((out / "batch-0001" / "batch_report.json").read_text())
    assert report["batch_id"] == "batch-0001"
    assert report["decision"] == "STOP_FOR_REVIEW"
    assert report["usage"]["total_estimated_cost_usd"] == 0.0


def test_batch_cli_requires_api_key_for_paid_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    rc = naturalize_and_run_batch.main(
        [
            "--batch-id",
            "batch-0001",
            "--batch-size",
            "10",
            "--out",
            str(tmp_path / "batches"),
        ]
    )

    assert rc == 2
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest tests/test_scripts/test_naturalize_and_run_batch.py -q
```

Expected: fails because the script does not exist.

- [ ] **Step 3: Implement dry-run and API-key gate**

Create `scripts/naturalize_and_run_batch.py`:

```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from clawsocialarena.llm.costing import TokenUsage
from clawsocialarena.llm.openai_client import OpenAIConfig, require_openai_key
from clawsocialarena.simulation.batch_runner import BatchUsage, build_batch_report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Naturalize and simulate one benchmark batch."
    )
    parser.add_argument("--batch-id", default="batch-0001")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--out", type=Path, default=Path("benchmark/batches"))
    parser.add_argument("--max-cost-usd", type=float, default=25.0)
    parser.add_argument("--construction-model", default=OpenAIConfig().construction_model)
    parser.add_argument("--agent-model", default=OpenAIConfig().agent_model)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.batch_size != 10:
        print("only --batch-size 10 is supported for the first pilot", file=sys.stderr)
        return 2
    if not args.dry_run:
        try:
            require_openai_key()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    scenario_ids = [f"pilot-placeholder-{idx:02d}" for idx in range(args.batch_size)]
    report = build_batch_report(
        batch_id=args.batch_id,
        scenario_ids=scenario_ids,
        accepted_scenario_ids=[],
        failed_scenarios=[],
        usage=BatchUsage(
            construction=TokenUsage(model=args.construction_model),
            simulation=TokenUsage(model=args.agent_model),
        ),
        stop_for_review=True,
    )
    report_path = args.out / args.batch_id / "batch_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(report.decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run CLI tests and verify pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_scripts/test_naturalize_and_run_batch.py -q
```

Expected: all tests pass.

## Task 6: Wire Real Naturalization and Simulation

**Files:**
- Modify: `clawsocialarena/generator/naturalization.py`
- Modify: `clawsocialarena/llm/openai_client.py`
- Modify: `clawsocialarena/simulation/batch_runner.py`
- Modify: `scripts/naturalize_and_run_batch.py`
- Test: `tests/test_generator/test_naturalization.py`
- Test: `tests/test_simulation/test_batch_runner.py`
- Test: `tests/test_scripts/test_naturalize_and_run_batch.py`

- [ ] **Step 1: Add mock OpenAI naturalization test**

Extend `tests/test_generator/test_naturalization.py` with a fake client that returns one `NaturalizationPatch`. Assert the naturalizer records model, prompt hash, cache key, and token usage.

- [ ] **Step 2: Add mock simulation test**

Extend `tests/test_simulation/test_batch_runner.py` with a fake simulation function. Assert accepted scenarios require `validate_bundle`, a scorecard path, and token usage aggregated from action logs.

- [ ] **Step 3: Implement real OpenAI call behind the wrapper**

Use the OpenAI SDK inside `clawsocialarena/llm/openai_client.py`. The wrapper should expose one method that accepts a JSON-schema prompt payload and returns parsed JSON plus usage fields. If the API response does not include cached token details, default cached input tokens to `0`.

- [ ] **Step 4: Implement naturalization prompt assembly**

Build the GPT-5 prompt from the scenario skeleton, ASB profile refs, world-pack resources, harm axis, attack type, and strict JSON schema. The system prompt must require synthetic content and prohibit real personal data.

- [ ] **Step 5: Implement simulation runner seam**

Run the naturalized bundle through the existing Docker compose path. If the OpenClaw agent model harness is not yet wired, fail with `simulation_status: failed` and an actionable message. Do not mark mock runs as simulation-passed.

- [ ] **Step 6: Run the mock test suite**

Run:

```bash
.venv/bin/python -m pytest tests/test_llm tests/test_generator/test_naturalization.py tests/test_simulation/test_batch_runner.py tests/test_scripts/test_naturalize_and_run_batch.py -q
```

Expected: all mock and dry-run tests pass without paid API calls.

## Task 7: First Paid Pilot Run

**Files:**
- Create/update: `benchmark/batches/batch-0001/**`

- [ ] **Step 1: Confirm prerequisites**

Run:

```bash
test -n "$OPENAI_API_KEY"
docker --version
.venv/bin/python -m pytest tests/test_llm tests/test_generator/test_naturalization.py tests/test_simulation/test_batch_runner.py tests/test_scripts/test_naturalize_and_run_batch.py -q
```

Expected: API key exists, Docker is available, and tests pass.

- [ ] **Step 2: Run first batch with hard cost cap**

Run:

```bash
.venv/bin/python scripts/naturalize_and_run_batch.py \
  --batch-id batch-0001 \
  --batch-size 10 \
  --max-cost-usd 25 \
  --construction-model gpt-5 \
  --agent-model gpt-4.1-mini \
  --out benchmark/batches
```

Expected: command stops after one batch and prints `STOP_FOR_REVIEW`.

- [ ] **Step 3: Report first-batch cost**

Read `benchmark/batches/batch-0001/batch_report.json` and report:

- accepted count
- failed count
- GPT-5 input, cached input, output tokens, and cost
- GPT-4.1 mini input, cached input, output tokens, and cost
- total batch cost
- observed cost per accepted scenario
- projected full 680-variant pilot cost with 25 percent and 50 percent buffers

- [ ] **Step 4: Stop for user review**

Do not run batch 2 until the user approves the cost and failure-rate profile.

## Task 8: Documentation Update

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-05-02-llm-naturalization-batch-pipeline-design.md`

- [ ] **Step 1: Add README section**

Document:

```bash
.venv/bin/python scripts/naturalize_and_run_batch.py \
  --batch-id batch-0001 \
  --batch-size 10 \
  --max-cost-usd 25
```

State that the command runs paid GPT-5 construction and GPT-4.1 mini agent simulation unless `--dry-run` is passed.

- [ ] **Step 2: Run docs tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_docs -q
```

Expected: docs tests pass.

## Task 9: Final Verification

**Files:**
- No planned edits.

- [ ] **Step 1: Run focused tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_llm tests/test_generator/test_naturalization.py tests/test_simulation/test_batch_runner.py tests/test_scripts/test_naturalize_and_run_batch.py -q
```

Expected: all focused tests pass.

- [ ] **Step 2: Run lint and type checks**

Run:

```bash
.venv/bin/python -m ruff check clawsocialarena/llm clawsocialarena/generator/naturalization.py clawsocialarena/simulation scripts/naturalize_and_run_batch.py tests/test_llm tests/test_generator/test_naturalization.py tests/test_simulation/test_batch_runner.py tests/test_scripts/test_naturalize_and_run_batch.py
.venv/bin/python -m mypy clawsocialarena/llm clawsocialarena/generator/naturalization.py clawsocialarena/simulation scripts/naturalize_and_run_batch.py tests/test_llm tests/test_generator/test_naturalization.py tests/test_simulation/test_batch_runner.py tests/test_scripts/test_naturalize_and_run_batch.py
```

Expected: ruff and mypy pass.

- [ ] **Step 3: Run full suite before claiming integration safety**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: no regressions beyond known skips.

## Self-Review

- The plan builds cost accounting before paid calls.
- The first paid run is capped at 10 scenarios and `$25`.
- The batch runner reports exact token and cost usage after the first batch.
- The first batch always stops for user review.
- The plan does not mark mock or dry-run execution as real simulation.
- The plan does not mark `llm_naturalized` data as release-ready without human review.
