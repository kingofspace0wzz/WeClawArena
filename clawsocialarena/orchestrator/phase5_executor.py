"""Phase 5 scenario executor surface (S4 step 2).

Defines the executor protocol that the orchestrator calls per row.
The mock executor returns deterministic results so the
orchestration logic stays testable without LLM calls; the live
executor (see :mod:`phase5_live_executor`) wraps gpt-5.2 naturalization
+ gpt-4.1-mini agent simulation and is exercised by Run-Batches 1..5.

Every executor returns a :class:`ScenarioResult` dataclass with the
columns the per-batch aggregator and the final PILOT_REPORT need.
The result is JSON-serializable so the orchestrator can persist it
to disk verbatim.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ScenarioResult:
    """The per-scenario outcome the orchestrator persists.

    The "rate" booleans are independently scored slots; the
    aggregator counts each one over rows where it is not ``None``.
    Critically, ``task_success`` and ``attack_success`` are
    **orthogonal** measurements: a scenario where the canonical
    task completed AND the attacker succeeded (e.g., orders
    exchanged AND the secondary's payment method leaked to the
    attacker) reports ``task_success=True`` AND
    ``attack_success=True`` on the same row.

    Column semantics (Run-Batch 1 wires only ``naturalization_success``;
    Run-Batches 2..5 wire the rest):

    - ``naturalization_success`` -- did gpt-5.2 produce a valid
      ``NaturalizationPatch`` for this scenario? Run-Batch 1's
      primary metric.
    - ``task_success`` -- did ``env_assertions`` against the
      bundle's ``evaluation_criteria`` pass after the agent loop?
    - ``attack_success`` -- generic flag; usually delegate to the
      per-axis columns below.
    - ``governance_violation`` -- did a state-mutating action
      commit without the required consent / authorization step?
      Defined for governance-mode rows.
    - ``privacy_violation`` -- did private data appear in
      attacker-visible channels (peer messages, exfil files)?
      Defined for privacy-mode rows.

    ``error`` is ``None`` on a clean run, or a short explanation if
    the scenario could not be executed. Errored scenarios are
    counted separately from failed ones in the batch report.
    """

    variant_id: str
    base_scenario_id: str
    cell_id: str
    family_id: str
    task_index: int
    tier_index: int | None  # None on v2 manifests (tier dimension dropped)
    attack_mode: str
    attack_recipe: str | None
    naturalization_success: bool | None
    task_success: bool | None
    # Per-axis attack-success columns. Each is defined only for rows
    # of that axis; the other three columns are ``None`` for that
    # row. Baseline (no_attacker) rows have all four as ``None``.
    # These are orthogonal to ``task_success``: a row can have
    # ``task_success=True`` AND any ``attack_success_*=True``.
    attack_success_collaboration: bool | None = None
    attack_success_security: bool | None = None
    attack_success_privacy: bool | None = None
    attack_success_governance: bool | None = None
    # Legacy aggregate attack_success column (deprecated; kept for
    # back-compat with R-B 1 readers). Equals OR of the four
    # per-axis columns when any are defined.
    attack_success: bool | None = None
    governance_violation: bool | None = None
    privacy_violation: bool | None = None
    compliance_ok: bool | None = None
    # SAF 6-dimension scorecard (0..1 per dim; ``None`` when not
    # scored). ``saf_overall`` is the weighted aggregate the
    # SAFScorer produces.
    saf_recoverability: float | None = None
    saf_policy_checkability: float | None = None
    saf_attribution: float | None = None
    saf_evidence_integrity: float | None = None
    saf_phase_scoped_policy: float | None = None
    saf_identity_governance: float | None = None
    saf_overall: float | None = None
    turn_count: int = 0
    hit_turn_cap: bool = False
    tool_call_count: int = 0
    """Number of ``TOOL_CALL`` rows recorded in the session
    action_log for this scenario. Used by the orchestrator's
    aggregator to compute per-mode tool-call rates and the
    baseline-corrected collaboration sidecar (Codex R-B 2 rerun
    review non-blocker)."""
    elapsed_seconds: float = 0.0
    naturalization_usage: dict[str, int] = field(default_factory=dict)
    simulation_usage: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    transcript_path: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class ScenarioExecutor(Protocol):
    """Anything callable that turns a manifest row + base_dir into a result.

    The orchestrator holds an executor and dispatches it per row. The
    mock executor implements this for tests; the live executor wraps
    the naturalization + simulation stack for production runs.
    """

    def execute(
        self,
        *,
        row: dict[str, Any],
        base_dir: Path,
    ) -> ScenarioResult: ...


# ---------- Mock executor ----------------------------------------------


@dataclass
class MockScenarioExecutor:
    """Deterministic executor used by orchestrator tests.

    Returns a synthetic but realistic ``ScenarioResult`` so the
    aggregator can be exercised end-to-end without LLM calls. The
    decision rules are:

    - baseline (no_attacker) rows succeed deterministically at task
      and have ``attack_success=None`` (no attacker present).
    - non-baseline rows succeed at task with probability tied to the
      attack_intensity (lower intensity = higher success), and
      record an ``attack_success`` that is the inverse.
    - governance / privacy violation flags depend on the row's
      attack_mode so each axis exercises a distinct column.

    Token usage is fabricated but consistent with a realistic gpt-5.2
    + gpt-4.1-mini call pattern so cost-aggregation logic stays
    exercised.
    """

    seed: int = 0
    base_naturalization_tokens: int = 1800
    base_simulation_tokens: int = 1200
    turns_per_scenario: int = 6

    def execute(
        self,
        *,
        row: dict[str, Any],
        base_dir: Path,
    ) -> ScenarioResult:
        attack_mode = row.get("attack_mode", "no_attacker")
        is_baseline = attack_mode == "no_attacker"
        # Deterministic pseudo-random from the variant_id so the
        # aggregator gets a non-uniform distribution to test against.
        # Use zlib.crc32 rather than Python's built-in hash() because
        # CPython salts hash() per process (PYTHONHASHSEED), so the
        # mock would produce different scores across process runs.
        digest_key = f"{self.seed}:{row.get('variant_id', '')}".encode("utf-8")
        deterministic_score = (zlib.crc32(digest_key) & 0xFFFF) / 0xFFFF
        attack_intensity = float(row.get("attack_intensity", 0.5))

        if is_baseline:
            task_success = deterministic_score > 0.1
            attack_success = None
        else:
            # Higher intensity = harder for the defender. Threshold
            # rises with intensity.
            task_success = deterministic_score > attack_intensity
            attack_success = not task_success

        governance_violation = (
            attack_mode == "governance" and bool(attack_success)
        )
        privacy_violation = attack_mode == "privacy" and bool(attack_success)
        compliance_ok = not (governance_violation or privacy_violation)

        return ScenarioResult(
            variant_id=row.get("variant_id", ""),
            base_scenario_id=row.get("base_scenario_id", ""),
            cell_id=row.get("cell_id", ""),
            family_id=row.get("family_id", ""),
            task_index=int(row.get("task_index", 0)),
            tier_index=int(v) if (v := row.get("tier_index")) is not None else None,
            attack_mode=attack_mode,
            attack_recipe=row.get("attack_recipe"),
            naturalization_success=True,
            task_success=task_success,
            attack_success=attack_success,
            governance_violation=governance_violation,
            privacy_violation=privacy_violation,
            compliance_ok=compliance_ok,
            turn_count=self.turns_per_scenario,
            elapsed_seconds=2.5,
            naturalization_usage={
                "prompt_tokens": self.base_naturalization_tokens,
                "completion_tokens": int(self.base_naturalization_tokens * 0.5),
                "total_tokens": int(self.base_naturalization_tokens * 1.5),
            },
            simulation_usage={
                "prompt_tokens": self.base_simulation_tokens,
                "completion_tokens": int(self.base_simulation_tokens * 0.5),
                "total_tokens": int(self.base_simulation_tokens * 1.5),
            },
            error=None,
            transcript_path=None,
            extra={"mock": True},
        )


# ---------- Error-injecting mock (for failure-path tests) --------------


@dataclass
class FailingMockExecutor:
    """A mock executor that always errors. Used in tests that assert
    the orchestrator counts errored scenarios separately.
    """

    error_message: str = "synthetic executor failure"

    def execute(
        self,
        *,
        row: dict[str, Any],
        base_dir: Path,
    ) -> ScenarioResult:
        return ScenarioResult(
            variant_id=row.get("variant_id", ""),
            base_scenario_id=row.get("base_scenario_id", ""),
            cell_id=row.get("cell_id", ""),
            family_id=row.get("family_id", ""),
            task_index=int(row.get("task_index", 0)),
            tier_index=int(v) if (v := row.get("tier_index")) is not None else None,
            attack_mode=row.get("attack_mode", "no_attacker"),
            attack_recipe=row.get("attack_recipe"),
            naturalization_success=None,
            task_success=None,
            attack_success=None,
            governance_violation=None,
            privacy_violation=None,
            compliance_ok=None,
            turn_count=0,
            elapsed_seconds=0.0,
            error=self.error_message,
            extra={"mock_failed": True},
        )
