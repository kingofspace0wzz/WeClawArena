"""Tests for the Phase-5 executor protocol + mocks (S4 step 2)."""
from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.orchestrator.phase5_executor import (
    FailingMockExecutor,
    MockScenarioExecutor,
    ScenarioResult,
)
from clawsocialarena.orchestrator.phase5_live_executor import (
    LiveScenarioExecutor,
)


_SAMPLE_ROW = {
    "variant_id": "CD-A-marble_research__t0__d1__no_attacker",
    "base_scenario_id": "CD-A-marble_research__t0__d1",
    "cell_id": "CD-A-marble_research",
    "family_id": "marble_research",
    "task_index": 0,
    "tier_index": 1,
    "attack_mode": "no_attacker",
    "attack_intensity": 0.4,
    "attack_recipe": None,
}


def test_mock_executor_returns_a_scenario_result() -> None:
    executor = MockScenarioExecutor()
    result = executor.execute(row=_SAMPLE_ROW, base_dir=Path("/tmp"))
    assert isinstance(result, ScenarioResult)
    assert result.variant_id == _SAMPLE_ROW["variant_id"]
    assert result.attack_mode == "no_attacker"


def test_mock_executor_is_deterministic_for_same_row_and_seed() -> None:
    a = MockScenarioExecutor(seed=42).execute(
        row=_SAMPLE_ROW, base_dir=Path("/tmp")
    )
    b = MockScenarioExecutor(seed=42).execute(
        row=_SAMPLE_ROW, base_dir=Path("/tmp")
    )
    assert a == b


def test_mock_executor_baseline_has_no_attack_success() -> None:
    """no_attacker rows should report ``attack_success=None`` so the
    aggregator does not score them as attack failures.
    """
    result = MockScenarioExecutor().execute(
        row=_SAMPLE_ROW, base_dir=Path("/tmp")
    )
    assert result.attack_success is None


def test_mock_executor_non_baseline_reports_attack_success_as_bool() -> None:
    row = {
        **_SAMPLE_ROW,
        "variant_id": "CD-A-marble_research__t0__d3__privacy",
        "attack_mode": "privacy",
        "attack_intensity": 0.8,
        "tier_index": 3,
        "attack_recipe": "collaborative_exfiltration",
    }
    result = MockScenarioExecutor().execute(row=row, base_dir=Path("/tmp"))
    assert isinstance(result.attack_success, bool)
    # privacy attack success implies a privacy_violation.
    if result.attack_success:
        assert result.privacy_violation is True
        assert result.compliance_ok is False


def test_failing_mock_executor_returns_error_result() -> None:
    result = FailingMockExecutor().execute(
        row=_SAMPLE_ROW, base_dir=Path("/tmp")
    )
    assert result.error is not None
    assert result.task_success is None
    assert result.attack_success is None


def test_live_executor_naturalization_only_in_run_batch_1() -> None:
    """Run-Batch 1 wired the live executor to naturalization-only.
    Calling it on a main-stratum row WITHOUT a stub client will try
    to instantiate the real OpenAI client, which fails without an
    API key. Supplementary rows still raise NotImplementedError
    until Run-Batch 5 wires them.
    """
    supp_row = {**_SAMPLE_ROW, "stratum": "supplementary"}
    with pytest.raises(NotImplementedError) as excinfo:
        LiveScenarioExecutor().execute(row=supp_row, base_dir=Path("/tmp"))
    assert "Run-Batch 5" in str(excinfo.value)
