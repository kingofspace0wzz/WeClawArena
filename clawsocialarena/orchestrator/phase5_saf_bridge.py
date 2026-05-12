"""SAF scoring bridge for the Phase-5 live executor.

Run-Batch 2 onward must surface the SAF 6-dimension scorecard
alongside task / attack success. The SAFScorer expects:

- ``action_log``: list[ActionRecord] (primary, hash-chained).
- ``shadow_log``: list[ActionRecord] (independent copy).
- ``produced_dag``: attribution DAG dict built from the records.
- ``gt``: the scenario's :class:`GTBundle`.
- ``mswm`` + ``mswm_snapshots``: replayed MSWM state.

The live executor holds a :class:`Session` with the audit
substrate already wired (under :data:`AuditCondition.PASSIVE`).
This bridge converts that substrate into the SAFScorer's input
contract by reusing the same helpers
:class:`~clawsocialarena.eval.runner.EvalRunner` uses, so the
Phase-5 pilot stays consistent with the offline evaluator.

The bridge intentionally does NOT depend on EvalRunner directly:
EvalRunner takes :class:`ActionLog` (DB-backed) and we want to be
able to score from in-memory record lists too (the agent loop
appends records via :meth:`Session._record_action`, and we read
them back at the end). The bridge handles both paths.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from clawsocialarena.audit.attribution import AttributionGraphBuilder
from clawsocialarena.audit.phase_tracker import PhaseTracker
from clawsocialarena.audit.policy_registry import PolicyRegistry
from clawsocialarena.audit.policy_catalog import PolicyCatalog
from clawsocialarena.gateway.session import Session
from clawsocialarena.saf.saf_scorer import DEFAULT_THRESHOLDS, SAFScorer
from clawsocialarena.saf.scorers import policy_checkability
from clawsocialarena.scenario.models import GTBundle
from clawsocialarena.types import ActionRecord


@dataclass
class SAFBridgeResult:
    """Flat representation of a :class:`SAFScorecard` for the executor.

    The Phase-5 :class:`ScenarioResult` carries one column per SAF
    dimension plus a weighted overall. The bridge populates them all
    from a single :class:`SAFScorecard` so the executor's per-row
    assembly stays declarative.
    """

    recoverability: float = 0.0
    policy_checkability: float = 0.0
    attribution: float = 0.0
    evidence_integrity: float = 0.0
    phase_scoped_policy: float = 0.0
    identity_governance: float = 0.0
    overall: float = 0.0
    passes: dict[str, bool] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    applicable_dims: list[str] = field(default_factory=list)
    not_applicable_dims: list[str] = field(default_factory=list)


def score_saf_from_session(
    *,
    session: Session,
    gt: GTBundle,
    catalog: PolicyCatalog | None = None,
    thresholds: dict[str, float] | None = None,
) -> SAFBridgeResult:
    """Score the run held by ``session`` against ``gt``.

    Reads the action_log and shadow_log directly off the session,
    builds the policy registry and phase tracker from the GT, and
    runs the SAFScorer the same way :class:`EvalRunner` does.

    BASELINE sessions have no log substrate and return a sentinel
    ``SAFBridgeResult`` with zeros and an explicit diagnostics
    note so the caller can branch on it. Run-Batch 2 always uses
    PASSIVE; the BASELINE path is here for forward compatibility.
    """
    if session.action_log is None or session.shadow_log is None:
        return SAFBridgeResult(
            diagnostics={"reason": "session_has_no_audit_substrate"}
        )

    a_records = list(session.action_log.read_all())
    s_records = list(session.shadow_log.read_all())
    return score_saf_from_records(
        action_log=a_records,
        shadow_log=s_records,
        gt=gt,
        catalog=catalog,
        thresholds=thresholds,
    )


def score_saf_from_records(
    *,
    action_log: list[ActionRecord],
    shadow_log: list[ActionRecord],
    gt: GTBundle,
    catalog: PolicyCatalog | None = None,
    thresholds: dict[str, float] | None = None,
) -> SAFBridgeResult:
    """Score a run from in-memory record lists.

    The Phase-5 agent loop appends records via ``Session`` helpers,
    which write into a SQLite-backed :class:`ActionLog`. For unit
    tests we want a path that bypasses the DB and feeds records
    directly. This function is that path.
    """
    catalog = catalog or PolicyCatalog()
    registry = _registry_from_gt(gt, catalog=catalog)
    pt = (
        PhaseTracker.from_schedule(gt.phase_schedule)
        if gt.phase_schedule
        else PhaseTracker()
    )
    mswm_snapshots = policy_checkability.snapshots_from_log(action_log)
    mswm = mswm_snapshots[-1] if mswm_snapshots else None
    produced_dag = AttributionGraphBuilder(
        action_log=action_log, mswm=mswm
    ).build()
    scorer = SAFScorer(
        policy_registry=registry,
        phase_tracker=pt,
        thresholds=thresholds,
    )
    scorecard = scorer.score(
        action_log=action_log,
        shadow_log=shadow_log,
        produced_dag=produced_dag,
        gt=gt,
        mswm=mswm,
        mswm_snapshots=mswm_snapshots,
    )
    applicability = scorecard.diagnostics.get("applicability", {})
    applicable = sorted(
        name for name, ok in applicability.items() if ok
    )
    not_applicable = sorted(
        name for name, ok in applicability.items() if not ok
    )
    return SAFBridgeResult(
        recoverability=scorecard.dims["recoverability"],
        policy_checkability=scorecard.dims["policy_checkability"],
        attribution=scorecard.dims["attribution"],
        evidence_integrity=scorecard.dims["evidence_integrity"],
        phase_scoped_policy=scorecard.dims["phase_scoped_policy"],
        identity_governance=scorecard.dims["identity_governance"],
        overall=scorecard.overall,
        passes=dict(scorecard.passes),
        diagnostics=dict(scorecard.diagnostics),
        applicable_dims=applicable,
        not_applicable_dims=not_applicable,
    )


def _registry_from_gt(
    gt: GTBundle, *, catalog: PolicyCatalog
) -> PolicyRegistry:
    reg = PolicyRegistry()
    for p in gt.policies.get("flat") or []:
        reg.register_flat(catalog.flat_from_dict(p))
    for p in gt.policies.get("phase_scoped") or []:
        reg.register_phase_scoped(catalog.phase_scoped_from_dict(p))
    return reg


# Re-export the threshold table so callers can adjust per-batch.
SAF_DEFAULT_THRESHOLDS = DEFAULT_THRESHOLDS


__all__ = [
    "SAFBridgeResult",
    "SAF_DEFAULT_THRESHOLDS",
    "score_saf_from_records",
    "score_saf_from_session",
]
