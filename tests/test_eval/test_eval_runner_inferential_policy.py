"""Phase F.5 Fix 1: MSWM ψ path must flow through EvalRunner + SAFScorer.

The legacy ψ surface scored only the flat-field ``required_fields``
decidability and never consulted ``GTBundle.policies['inferential']``. As
a result any vignette carrying an inferential-leakage invariant would
silently score ψ = 1.0 even when the MSWM proved the target agent could
already combine every item in the forbidden set.

These tests build tiny multi-agent action logs, attach inferential
policies to the GT bundle, and drive :class:`EvalRunner` end-to-end.
The assertions pin:

1. An undecidable inferential policy drops ψ below 1.0, proving the
   snapshots are threaded through SAFScorer.
2. The inferential numerator sums with the flat numerator: a
   mixed-bucket bundle reports ψ as
   ``(decidable_flat + decidable_inferential) / (declared_flat +
   declared_inferential)``.
3. A bundle with no inferential bucket (legacy shape) keeps ψ == 1.0
   when both sides are empty; the backward-compat default is preserved.
"""

from __future__ import annotations

from pathlib import Path

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.shadow_log import ShadowLog
from clawsocialarena.eval.runner import EvalRunner
from clawsocialarena.scenario.models import GTBundle
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


def _append_outbound(
    log: ActionLog,
    agent: str,
    idx: int,
    recipient: str,
    mentioned: list[str],
) -> None:
    prev = log.head_hash(agent)
    rec = ActionRecord(
        action_id=f"{agent}-{idx}",
        prev_hash=prev,
        agent_id=agent,
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-17T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCLOSURE,
        payload={
            "recipient_id": recipient,
            "content": f"msg-{idx}",
            "mentioned_items": list(mentioned),
        },
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )
    log.append(rec)


def _build_three_agent_log(tmp_path: Path) -> tuple[ActionLog, ShadowLog]:
    """Return (primary, shadow) logs with the task-prescribed three-agent trace.

    Action 0: Alice discloses ``med_x`` to Charlie.
    Action 1: Bob discloses ``condition_y`` to Charlie.

    After both actions, Charlie's MSWM holds {med_x, condition_y} via
    ``items_learned_from_j``; any policy forbidding Charlie from
    jointly deciding that pair evaluates to ``violated`` under
    :meth:`MSWM.joint_decidability`.
    """

    primary = ActionLog(tmp_path / "primary.db")
    shadow = ShadowLog(tmp_path / "shadow.db")

    _append_outbound(primary, "alice", 0, "charlie", ["med_x"])
    _append_outbound(shadow, "alice", 0, "charlie", ["med_x"])
    _append_outbound(primary, "bob", 1, "charlie", ["condition_y"])
    _append_outbound(shadow, "bob", 1, "charlie", ["condition_y"])

    return primary, shadow


def test_undecidable_inferential_policy_drops_psi(tmp_path: Path) -> None:
    """Policy references an item never observed in the log → undecidable.

    The inferential numerator excludes undecidable verdicts, so ψ drops
    from 1.0 down to the flat-only fraction (here 0 flat declared, so
    ψ = decidable_inf / declared_inf = 0/1 = 0.0).
    """

    primary, shadow = _build_three_agent_log(tmp_path)
    gt = GTBundle(
        scenario_id="phase-F5-fix1-undecidable",
        canonical_action_stream=[],
        phase_schedule=[],
        policies={
            "flat": [],
            "phase_scoped": [],
            "inferential": [
                {
                    "policy_id": "charlie-mystery-pair",
                    "evaluation_turn": 2,
                    "type": "must_not_decide",
                    "for_agent": "charlie",
                    # ``mystery_item`` never appears anywhere in the log.
                    "forbidden_inference": ["med_x", "mystery_item"],
                }
            ],
        },
        attribution_dag={"nodes": [], "edges": []},
        integrity_requirements={},
        terminal_predicate={"type": "none"},
        invariants={},
    )

    runner = EvalRunner()
    sc = runner.evaluate(action_log=primary, shadow_log=shadow, gt=gt)

    psi = sc.saf.dims["policy_checkability"]
    assert psi < 1.0, (
        f"Undecidable inferential policy should drop ψ below 1.0; got {psi}"
    )
    # Because no flat policies are declared and the only inferential
    # policy is undecidable, ψ is exactly 0.0.
    assert psi == 0.0


def test_violated_inferential_policy_counts_as_decidable(tmp_path: Path) -> None:
    """Charlie holds both items → verdict 'violated' → counts as decidable.

    The numerator rule follows spec §3.2: definite verdicts ('decidable'
    or 'violated') enter the numerator. Only 'undecidable' is excluded.
    Task description: a 'decidable_and_violated' verdict keeps ψ at 1.0
    while still proving the inferential path is live.
    """

    primary, shadow = _build_three_agent_log(tmp_path)
    gt = GTBundle(
        scenario_id="phase-F5-fix1-violated",
        canonical_action_stream=[],
        phase_schedule=[],
        policies={
            "flat": [],
            "phase_scoped": [],
            "inferential": [
                {
                    "policy_id": "charlie-forbidden-pair",
                    "evaluation_turn": 2,
                    "type": "must_not_decide",
                    "for_agent": "charlie",
                    "forbidden_inference": ["med_x", "condition_y"],
                }
            ],
        },
        attribution_dag={"nodes": [], "edges": []},
        integrity_requirements={},
        terminal_predicate={"type": "none"},
        invariants={},
    )

    runner = EvalRunner()
    sc = runner.evaluate(action_log=primary, shadow_log=shadow, gt=gt)

    # violated counts toward the decidable numerator.
    assert sc.saf.dims["policy_checkability"] == 1.0


def test_mixed_flat_and_inferential_buckets_sum_correctly(tmp_path: Path) -> None:
    """ψ = (decidable_flat + decidable_inferential) / (declared_flat +
    declared_inferential). Both buckets contribute to numerator and
    denominator.
    """

    primary, shadow = _build_three_agent_log(tmp_path)
    gt = GTBundle(
        scenario_id="phase-F5-fix1-mixed",
        canonical_action_stream=[],
        phase_schedule=[],
        policies={
            "flat": [
                # required_fields=payload.content is present on every
                # OUTBOUND_MESSAGE record, so this flat policy is
                # decidable (1/1 on the flat side).
                {
                    "policy_id": "flat-content-present",
                    "kind": "always_true",
                    "required_fields": ["payload.content"],
                }
            ],
            "phase_scoped": [],
            "inferential": [
                {
                    # undecidable: item "zzz" was never observed.
                    "policy_id": "undecidable",
                    "evaluation_turn": 2,
                    "type": "must_not_decide",
                    "for_agent": "charlie",
                    "forbidden_inference": ["zzz"],
                }
            ],
        },
        attribution_dag={"nodes": [], "edges": []},
        integrity_requirements={},
        terminal_predicate={"type": "none"},
        invariants={},
    )

    runner = EvalRunner()
    sc = runner.evaluate(action_log=primary, shadow_log=shadow, gt=gt)

    # Flat: 1 declared / 1 decidable. Inferential: 1 declared / 0
    # decidable (undecidable verdict). ψ = (1 + 0) / (1 + 1) = 0.5.
    assert sc.saf.dims["policy_checkability"] == 0.5


def test_inferential_bucket_missing_defaults_to_legacy_flat(tmp_path: Path) -> None:
    """Legacy GT bundles without an ``inferential`` key keep ψ == 1.0 when
    no flat policies are declared either. Proves backward compatibility."""

    primary, shadow = _build_three_agent_log(tmp_path)
    gt = GTBundle(
        scenario_id="phase-F5-fix1-legacy",
        canonical_action_stream=[],
        phase_schedule=[],
        # No "inferential" key at all (v1 shape).
        policies={"flat": [], "phase_scoped": []},
        attribution_dag={"nodes": [], "edges": []},
        integrity_requirements={},
        terminal_predicate={"type": "none"},
        invariants={},
    )

    runner = EvalRunner()
    sc = runner.evaluate(action_log=primary, shadow_log=shadow, gt=gt)

    assert sc.saf.dims["policy_checkability"] == 1.0
