"""EvalRunner — 5-stage pure-function scoring pipeline.

Stages:
1. Log integrity check (verify_chain per agent).
2. Trace reconstruction (read all records).
3. SAF scoring (5 dimensions).
4. Task / privacy / security scoring (placeholders; filled in Phase 3+).
5. Diagnostics (placeholders; filled in Phase 3+).

Per spec §6, evaluation is offline and pure. Given identical inputs,
scoring is bit-for-bit reproducible.

The PolicyRegistry is constructed fresh per evaluate() call from
`gt.policies` via the PolicyCatalog. This ensures that identical logs + GT
always yield the same scorecard, independent of how EvalRunner was built.
"""

from __future__ import annotations

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.attribution import AttributionGraphBuilder
from clawsocialarena.audit.phase_tracker import PhaseTracker
from clawsocialarena.audit.policy_catalog import PolicyCatalog
from clawsocialarena.audit.policy_registry import PolicyRegistry
from clawsocialarena.eval.scorecard import (
    PrivacyScorecard,
    RunScorecard,
    SAFDimsPayload,
    SecurityScorecard,
    TaskScorecard,
)
from clawsocialarena.saf.saf_scorer import SAFScorer
from clawsocialarena.scenario.models import GTBundle


class EvalRunner:
    def __init__(self, *, catalog: PolicyCatalog | None = None) -> None:
        self._catalog = catalog or PolicyCatalog()

    def _build_registry(self, gt: GTBundle) -> PolicyRegistry:
        reg = PolicyRegistry()
        for p in (gt.policies.get("flat") or []):
            reg.register_flat(self._catalog.flat_from_dict(p))
        for p in (gt.policies.get("phase_scoped") or []):
            reg.register_phase_scoped(self._catalog.phase_scoped_from_dict(p))
        return reg

    def evaluate(
        self,
        *,
        action_log: ActionLog,
        shadow_log: ActionLog,
        gt: GTBundle,
    ) -> RunScorecard:
        # Stage 1 — Integrity check (non-fatal: we surface in diagnostics)
        a_records = action_log.read_all()
        s_records = shadow_log.read_all()
        agents = {r.agent_id for r in a_records} | {r.agent_id for r in s_records}
        chain_ok_primary = {aid: action_log.verify_chain(aid) for aid in agents}
        chain_ok_shadow = {aid: shadow_log.verify_chain(aid) for aid in agents}

        # Stage 2 — Trace reconstruction (already done via read_all)

        # Stage 3 — SAF scoring
        registry = self._build_registry(gt)
        pt = (
            PhaseTracker.from_schedule(gt.phase_schedule)
            if gt.phase_schedule
            else PhaseTracker()
        )
        scorer = SAFScorer(policy_registry=registry, phase_tracker=pt)
        saf_result = scorer.score(
            action_log=a_records,
            shadow_log=s_records,
            produced_dag=AttributionGraphBuilder().build(action_log=a_records),
            gt=gt,
        )

        # Stage 4 — Task / privacy / security (placeholders for Phase 2)
        task = TaskScorecard(tsr=1.0)
        privacy = PrivacyScorecard()
        security = SecurityScorecard()

        # Stage 5 — Diagnostics
        diagnostics = {
            "chain_integrity_primary": chain_ok_primary,
            "chain_integrity_shadow": chain_ok_shadow,
            "log_row_count_primary": len(a_records),
            "log_row_count_shadow": len(s_records),
            "flat_policies_registered": len(registry.flat_policies),
            "phase_scoped_policies_registered": len(registry.scoped_policies),
        }

        saf_payload = SAFDimsPayload(
            dims=saf_result.dims,
            passes=saf_result.passes,
            overall=saf_result.overall,
        )

        return RunScorecard(
            scenario_id=gt.scenario_id,
            saf=saf_payload,
            task=task,
            privacy=privacy,
            security=security,
            diagnostics=diagnostics,
        )
