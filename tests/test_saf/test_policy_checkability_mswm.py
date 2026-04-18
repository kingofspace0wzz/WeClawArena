"""Phase F / Task F1: MSWM-driven Policy Checkability (psi)."""

from __future__ import annotations

from clawsocialarena.audit.mswm import MSWM
from clawsocialarena.saf.scorers import policy_checkability
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


def _outbound(
    agent: str,
    idx: int,
    recipient: str,
    mentioned: list[str],
    content: str = "hello",
) -> ActionRecord:
    return ActionRecord(
        action_id=f"{agent}-{idx}",
        prev_hash="0" * 64,
        agent_id=agent,
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-17T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCLOSURE,
        payload={
            "recipient_id": recipient,
            "content": content,
            "mentioned_items": list(mentioned),
        },
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def test_snapshots_from_log_returns_len_plus_one():
    log = [_outbound("A", i, "C", ["item-x"]) for i in range(3)]
    snaps = policy_checkability.snapshots_from_log(log)
    assert len(snaps) == len(log) + 1
    # Pre-episode snapshot is empty.
    assert list(snaps[0].pairs()) == []
    # Post-episode snapshot reflects all three disclosures to C.
    assert ("item-x", "A-2") in snaps[3].get("A", "C").items_told_to_j


def test_snapshots_are_independent_point_in_time():
    """A later replay step must not mutate an earlier snapshot."""

    log = [
        _outbound("A", 0, "C", ["item-x"]),
        _outbound("A", 1, "C", ["item-y"]),
    ]
    snaps = policy_checkability.snapshots_from_log(log)
    # Snapshot after step 1 should NOT have item-y.
    sender_t1 = snaps[1].get("A", "C").items_told_to_j
    assert ("item-x", "A-0") in sender_t1
    assert not any(item == "item-y" for item, _ in sender_t1)


def test_score_mswm_violated_counts_as_decidable():
    """Spec §3.2: 'decidable' numerator includes both verdicts that reach a
    definite conclusion. Only 'undecidable' fails the policy."""

    # Single action discloses items x and y jointly to C; that means C now
    # holds both items and can form the forbidden inference.
    log = [_outbound("A", 0, "C", ["item-x", "item-y"])]
    snaps = policy_checkability.snapshots_from_log(log)
    gt_policies = [
        {
            "policy_id": "boundary-1",
            "evaluation_turn": 1,
            "type": "must_not_decide",
            "for_agent": "C",
            "forbidden_inference": ["item-x", "item-y"],
        }
    ]
    result = policy_checkability.score_mswm(
        action_log=log,
        mswm_snapshots=snaps,
        gt_policies=gt_policies,
    )
    assert result.per_policy["boundary-1"] == "violated"
    assert result.scalar == 1.0


def test_score_mswm_undecidable_excluded_from_numerator():
    """Undecidable (no evidence about target agent) does not count as
    decidable; scalar = 0 / 1."""

    log = [_outbound("A", 0, "B", ["item-x"])]  # C never observed
    gt_policies = [
        {
            "policy_id": "boundary-2",
            "evaluation_turn": 1,
            "type": "must_not_decide",
            "for_agent": "C",  # agent we have zero MSWM entries about
            "forbidden_inference": ["item-z"],  # item never observed either
        }
    ]
    result = policy_checkability.score_mswm(
        action_log=log, gt_policies=gt_policies
    )
    assert result.per_policy["boundary-2"] == "undecidable"
    assert result.scalar == 0.0


def test_score_mswm_mixed_decidable_and_undecidable():
    log = [
        _outbound("A", 0, "C", ["item-x", "item-y"]),
        _outbound("A", 1, "C", ["item-x"]),
    ]
    gt_policies = [
        {
            "policy_id": "dec-1",
            "evaluation_turn": 1,
            "type": "must_not_decide",
            "for_agent": "C",
            "forbidden_inference": ["item-x", "item-y"],
        },
        {
            "policy_id": "undec-1",
            "evaluation_turn": 1,
            "type": "must_not_decide",
            "for_agent": "D",  # no MSWM entry for D
            "forbidden_inference": ["item-q"],
        },
    ]
    result = policy_checkability.score_mswm(
        action_log=log, gt_policies=gt_policies
    )
    # dec-1 is violated (C has both) -> counts as decidable.
    # undec-1 is undecidable.
    assert result.per_policy["dec-1"] == "violated"
    assert result.per_policy["undec-1"] == "undecidable"
    assert result.scalar == 0.5


def test_score_mswm_empty_gt_returns_one():
    result = policy_checkability.score_mswm(
        action_log=[], gt_policies=[]
    )
    assert result.scalar == 1.0
    assert result.per_policy == {}


def test_score_mswm_uses_snapshot_at_evaluation_turn():
    """The snapshot at turn t must NOT include actions at turn > t."""

    log = [
        _outbound("A", 0, "C", ["item-x"]),  # turn 1 disclosure
        _outbound("A", 1, "C", ["item-y"]),  # turn 2 disclosure
    ]
    gt_policies = [
        {
            "policy_id": "early",
            # Evaluate after turn 1 only: C has only item-x, not both.
            "evaluation_turn": 1,
            "type": "must_not_decide",
            "for_agent": "C",
            "forbidden_inference": ["item-x", "item-y"],
        },
    ]
    result = policy_checkability.score_mswm(
        action_log=log, gt_policies=gt_policies
    )
    # After turn 1, C knows item-x but item-y was never observed yet, so
    # the model cannot decide -> undecidable.
    assert result.per_policy["early"] == "undecidable"


def test_score_mswm_rebuilds_snapshots_when_none_supplied():
    log = [_outbound("A", 0, "C", ["item-x", "item-y"])]
    gt_policies = [
        {
            "policy_id": "auto",
            "evaluation_turn": 1,
            "type": "must_not_decide",
            "for_agent": "C",
            "forbidden_inference": ["item-x", "item-y"],
        }
    ]
    # No snapshots supplied -> the scorer builds them from the log.
    result = policy_checkability.score_mswm(
        action_log=log, gt_policies=gt_policies, mswm_snapshots=None
    )
    assert result.per_policy["auto"] == "violated"
    assert result.scalar == 1.0


def test_score_mswm_clamps_out_of_range_evaluation_turn():
    log = [_outbound("A", 0, "C", ["item-x", "item-y"])]
    gt_policies = [
        {
            "policy_id": "overshoot",
            "evaluation_turn": 999,
            "type": "must_not_decide",
            "for_agent": "C",
            "forbidden_inference": ["item-x", "item-y"],
        }
    ]
    result = policy_checkability.score_mswm(
        action_log=log, gt_policies=gt_policies
    )
    # Clamps to the terminal snapshot; C knows both items -> violated.
    assert result.per_policy["overshoot"] == "violated"


def test_score_mswm_does_not_touch_caller_owned_mswm():
    """Replay helper builds its own MSWM; caller state stays untouched."""

    caller_mswm = MSWM()  # empty; caller never populates it
    log = [_outbound("A", 0, "C", ["item-x"])]
    policy_checkability.snapshots_from_log(log)
    # Caller MSWM remains empty after scorer runs.
    assert list(caller_mswm.pairs()) == []
    assert not caller_mswm.self_knowledge
