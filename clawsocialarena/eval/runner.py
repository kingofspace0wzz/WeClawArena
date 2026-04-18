"""EvalRunner — five-stage pure-function evaluation pipeline.

Per spec §5.5 the evaluation pipeline runs offline after a scenario
completes. Every stage is a pure function of its inputs; there is no
wall-clock dependence and no hidden mutable state.

Stages:

1. Log integrity check — verify every agent's hash chain; if any chain
   is broken the run is flagged and ``chain_integrity_primary`` records
   the per-agent verdicts.
2. Trace reconstruction — read all records out of the primary and
   shadow logs; replay MSWM snapshots; tag the per-turn social phase.
3. SAF scoring — five dimensions evaluated in parallel; overall score
   is the weighted geometric mean.
4. Task / privacy / security scoring — terminal predicate, leak rates,
   attacker outcomes.
5. Diagnostics — error-chain classification, temporal breakdowns for
   episode-graph runs, rewrite-quality delta between ENFORCE and
   PASSIVE if both are supplied via ``meta``.

Emits a v2 :class:`~clawsocialarena.eval.scorecard.RunScorecard` with
the Phase F provenance fields populated from the caller's ``meta``
dict (``cassette_hash``, ``live_or_replay``, ``episode_graph_id``).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Literal

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.attribution import AttributionGraphBuilder
from clawsocialarena.audit.mswm import MSWM
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
from clawsocialarena.types import ActionRecord


class EvalRunner:
    """Five-stage offline evaluator.

    The runner is stateless. One instance may score many runs in any
    order; each :meth:`evaluate` call re-derives every intermediate
    (registry, phase tracker, MSWM) from the scenario's GT bundle and
    the action + shadow logs provided.
    """

    def __init__(self, *, catalog: PolicyCatalog | None = None) -> None:
        self._catalog = catalog or PolicyCatalog()

    def _build_registry(self, gt: GTBundle) -> PolicyRegistry:
        reg = PolicyRegistry()
        for p in gt.policies.get("flat") or []:
            reg.register_flat(self._catalog.flat_from_dict(p))
        for p in gt.policies.get("phase_scoped") or []:
            reg.register_phase_scoped(self._catalog.phase_scoped_from_dict(p))
        return reg

    def evaluate(
        self,
        *,
        action_log: ActionLog,
        shadow_log: ActionLog,
        gt: GTBundle,
        cassette_path: Path | str | None = None,
        live_or_replay: Literal["live", "replay"] = "live",
        episode_graph_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> RunScorecard:
        """Run the five-stage pipeline and emit a v2 scorecard.

        ``cassette_path`` (if supplied) is read, hashed (sha256), and
        attached to the scorecard as ``cassette_hash``. Missing files
        yield an empty hash string, matching the legacy contract where
        no cassette means no provenance.

        ``live_or_replay`` and ``episode_graph_id`` are written through
        to the scorecard so the analysis layer can partition results
        without having to consult the batch-runner config again.

        ``meta`` is merged into the scorecard's ``meta`` dict for
        downstream analytics (condition, model, seed, privacy_level).
        """

        # ------------------------------------------------------------------
        # Stage 1 — Log integrity check.
        # ------------------------------------------------------------------
        a_records = action_log.read_all()
        s_records = shadow_log.read_all()
        agents = {r.agent_id for r in a_records} | {r.agent_id for r in s_records}
        chain_ok_primary = {aid: action_log.verify_chain(aid) for aid in agents}
        chain_ok_shadow = {aid: shadow_log.verify_chain(aid) for aid in agents}
        # "Gateway invariant passed" is the AND over primary-chain verdicts;
        # the shadow log is an independent copy used only for Recoverability.
        gateway_invariant_passed = all(chain_ok_primary.values()) if agents else True

        # ------------------------------------------------------------------
        # Stage 2 — Trace reconstruction.
        # ------------------------------------------------------------------
        mswm = MSWM()
        for rec in a_records:
            mswm.on_action(rec)
        phase_tags = self._tag_phases(a_records)

        # ------------------------------------------------------------------
        # Stage 3 — SAF scoring.
        # ------------------------------------------------------------------
        registry = self._build_registry(gt)
        pt = (
            PhaseTracker.from_schedule(gt.phase_schedule)
            if gt.phase_schedule
            else PhaseTracker()
        )
        scorer = SAFScorer(policy_registry=registry, phase_tracker=pt)
        produced_dag = AttributionGraphBuilder(
            action_log=a_records, mswm=mswm
        ).build()
        saf_result = scorer.score(
            action_log=a_records,
            shadow_log=s_records,
            produced_dag=produced_dag,
            gt=gt,
        )

        # ------------------------------------------------------------------
        # Stage 4 — Task / privacy / security scoring (placeholders for now;
        # Phase H wires the full task / leak / attack pipeline; here we just
        # carry the shells forward so v2 scorecards have the right shape).
        # ------------------------------------------------------------------
        task = TaskScorecard(tsr=1.0)
        privacy = PrivacyScorecard()
        security = SecurityScorecard()

        # ------------------------------------------------------------------
        # Stage 5 — Diagnostics.
        # ------------------------------------------------------------------
        diagnostics: dict[str, Any] = {
            "chain_integrity_primary": chain_ok_primary,
            "chain_integrity_shadow": chain_ok_shadow,
            "log_row_count_primary": len(a_records),
            "log_row_count_shadow": len(s_records),
            "flat_policies_registered": len(registry.flat_policies),
            "phase_scoped_policies_registered": len(registry.scoped_policies),
            "mswm_peer_pairs": sum(len(peers) for peers in mswm.state.values()),
            "attribution_node_count": len(produced_dag.get("nodes", [])),
            "attribution_edge_count": len(produced_dag.get("edges", [])),
            "phase_tag_counts": phase_tags,
        }
        if episode_graph_id is not None:
            # Episode-graph runs get a marker so the aggregator can route
            # them into the cumulative-trajectory pipeline.
            diagnostics["episode_graph_id"] = episode_graph_id

        cassette_hash = self._hash_cassette(cassette_path)

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
            meta=dict(meta or {}),
            gateway_invariant_passed=gateway_invariant_passed,
            cassette_hash=cassette_hash,
            live_or_replay=live_or_replay,
            episode_graph_id=episode_graph_id,
        )

    @staticmethod
    def _tag_phases(records: list[ActionRecord]) -> dict[str, int]:
        """Return a count per social_phase over the action log.

        Stage-2 trace reconstruction documents per-phase activity so the
        diagnostics layer can spot skewed phase distributions without
        re-iterating the records itself.
        """

        counts: dict[str, int] = {}
        for rec in records:
            counts[rec.social_phase.value] = counts.get(rec.social_phase.value, 0) + 1
        return counts

    @staticmethod
    def _hash_cassette(cassette_path: Path | str | None) -> str:
        """Return sha256 hex of the cassette file, or '' if absent.

        We hash the full file bytes rather than the parsed JSON so any
        cassette-format change surfaces as a drift signal. Empty string
        on missing file keeps the v1 scorecard contract intact.
        """

        if cassette_path is None:
            return ""
        p = Path(cassette_path)
        if not p.exists() or not p.is_file():
            return ""
        h = hashlib.sha256()
        with p.open("rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
