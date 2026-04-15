from clawsocialarena.audit.phase_tracker import PhaseTracker
from clawsocialarena.audit.policy_registry import (
    FlatPolicy,
    PhaseScopedPolicy,
    PolicyRegistry,
)
from clawsocialarena.saf.scorers import (
    attribution_dag,
    evidence_integrity,
    phase_scoped_policy,
    policy_checkability,
    recoverability,
)
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


def _mk(agent: str, idx: int, level: IntegrityLevel = IntegrityLevel.HASH_CHAINED,
        phase: SocialPhase = SocialPhase.DISCOVERY,
        payload: dict | None = None) -> ActionRecord:
    return ActionRecord(
        action_id=f"{agent}-{idx}",
        prev_hash="0" * 64,
        agent_id=agent,
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-15T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=phase,
        payload=payload if payload is not None else {"content": f"msg-{idx}"},
        integrity_level=level,
    )


# --- Recoverability ---------------------------------------------------------

def test_recoverability_perfect_match():
    shadow = [_mk("a", i) for i in range(5)]
    log = list(shadow)
    assert recoverability.score(action_log=log, shadow_log=shadow) == 1.0


def test_recoverability_missing_actions():
    shadow = [_mk("a", i) for i in range(5)]
    log = shadow[:3]
    assert recoverability.score(action_log=log, shadow_log=shadow) == 0.6


def test_recoverability_empty_shadow_is_one():
    assert recoverability.score(action_log=[], shadow_log=[]) == 1.0


def test_recoverability_detects_tampered_payload():
    shadow = [_mk("a", i) for i in range(3)]
    # Primary has same IDs but tampered payload on action a-1
    log = [_mk("a", 0), _mk("a", 1, payload={"content": "TAMPERED"}), _mk("a", 2)]
    # Only a-0 and a-2 match exactly
    assert recoverability.score(action_log=log, shadow_log=shadow) == 2 / 3


def test_recoverability_ignores_primary_extras():
    """Spec formula = |log ∩ gt| / |gt|. Primary extras don't change the score
    as long as all GT records are present."""
    shadow = [_mk("a", i) for i in range(3)]
    log = shadow + [_mk("a", 99)]  # extra record not in shadow
    assert recoverability.score(action_log=log, shadow_log=shadow) == 1.0


# --- Evidence Integrity ----------------------------------------------------

def test_evidence_integrity_all_meets_requirement():
    reqs = {"outbound_message": IntegrityLevel.HASH_CHAINED}
    log = [_mk("a", i) for i in range(3)]
    s = evidence_integrity.score(action_log=log, integrity_requirements=reqs)
    # weight for hash_chained = 0.75; all 3 meet -> 0.75
    assert abs(s - 0.75) < 1e-9


def test_evidence_integrity_under_requirement():
    reqs = {"outbound_message": IntegrityLevel.CROSS_AGENT_SIGNED}
    log = [_mk("a", i) for i in range(3)]  # HASH_CHAINED, doesn't meet level 4
    s = evidence_integrity.score(action_log=log, integrity_requirements=reqs)
    assert s == 0.0


def test_evidence_integrity_no_requirements_is_one():
    reqs = {}
    log = [_mk("a", i) for i in range(2)]
    assert evidence_integrity.score(action_log=log, integrity_requirements=reqs) == 1.0


# --- Policy Checkability ---------------------------------------------------

def test_policy_checkability_all_decidable():
    reg = PolicyRegistry()
    reg.register_flat(FlatPolicy(
        policy_id="p1",
        predicate=lambda a, ctx: True,
        required_fields={"payload.content"},
    ))
    log = [_mk("a", 0)]  # payload has content
    assert policy_checkability.score(action_log=log, policy_registry=reg) == 1.0


def test_policy_checkability_missing_field():
    reg = PolicyRegistry()
    reg.register_flat(FlatPolicy(
        policy_id="p1",
        predicate=lambda a, ctx: True,
        required_fields={"payload.nonexistent"},
    ))
    log = [_mk("a", 0)]
    assert policy_checkability.score(action_log=log, policy_registry=reg) == 0.0


def test_policy_checkability_no_policies_is_one():
    reg = PolicyRegistry()
    log = [_mk("a", 0)]
    assert policy_checkability.score(action_log=log, policy_registry=reg) == 1.0


def test_policy_checkability_requires_fields_in_same_record():
    """Field A in record 1 + field B in record 2 should NOT count as decidable."""
    reg = PolicyRegistry()
    reg.register_flat(FlatPolicy(
        policy_id="p1",
        predicate=lambda a, ctx: True,
        required_fields={"payload.a_only", "payload.b_only"},
    ))
    log = [
        _mk("a", 0, payload={"a_only": 1}),    # has a_only, no b_only
        _mk("a", 1, payload={"b_only": 2}),    # has b_only, no a_only
    ]
    # No single record has both -> not decidable
    assert policy_checkability.score(action_log=log, policy_registry=reg) == 0.0


def test_policy_checkability_decidable_when_fields_in_same_record():
    """Field A and field B both in one record -> decidable."""
    reg = PolicyRegistry()
    reg.register_flat(FlatPolicy(
        policy_id="p1",
        predicate=lambda a, ctx: True,
        required_fields={"payload.a_only", "payload.b_only"},
    ))
    log = [
        _mk("a", 0, payload={"a_only": 1, "b_only": 2}),
    ]
    assert policy_checkability.score(action_log=log, policy_registry=reg) == 1.0


# --- Attribution DAG -------------------------------------------------------

def test_attribution_identical_dags():
    gt = {"nodes": [], "edges": [{"src": "A", "dst": "B", "label": "L0"}]}
    produced = {"nodes": [], "edges": [{"src": "A", "dst": "B", "label": "L0"}]}
    assert attribution_dag.score(produced_dag=produced, gt_dag=gt) == 1.0


def test_attribution_missed_edge():
    gt = {"nodes": [], "edges": [
        {"src": "A", "dst": "B", "label": "L0"},
        {"src": "B", "dst": "C", "label": "L1"},
    ]}
    produced = {"nodes": [], "edges": [{"src": "A", "dst": "B", "label": "L0"}]}
    s = attribution_dag.score(produced_dag=produced, gt_dag=gt)
    # F1: tp=1, precision=1.0, recall=0.5 -> F1 = 2 * 1 * 0.5 / 1.5 = 2/3
    assert abs(s - 2 / 3) < 1e-9


def test_attribution_empty_both_is_one():
    gt = {"nodes": [], "edges": []}
    produced = {"nodes": [], "edges": []}
    assert attribution_dag.score(produced_dag=produced, gt_dag=gt) == 1.0


def test_attribution_empty_gt_with_predictions_is_zero():
    gt = {"nodes": [], "edges": []}
    produced = {"nodes": [], "edges": [{"src": "X", "dst": "Y", "label": "L0"}]}
    assert attribution_dag.score(produced_dag=produced, gt_dag=gt) == 0.0


# --- Phase-Scoped Policy --------------------------------------------------

def test_phase_scoped_policy_all_satisfied_and_decidable():
    reg = PolicyRegistry()
    reg.register_phase_scoped(PhaseScopedPolicy(
        policy_id="p1",
        phase=SocialPhase.DISCOVERY,
        predicate=lambda a, ctx: True,
        required_fields={"payload.content"},
    ))
    pt = PhaseTracker()
    log = [_mk("a", 0, phase=SocialPhase.DISCOVERY)]
    result = phase_scoped_policy.score(
        action_log=log, policy_registry=reg, phase_tracker=pt
    )
    assert result.scalar == 1.0


def test_phase_scoped_policy_one_violation():
    reg = PolicyRegistry()
    reg.register_phase_scoped(PhaseScopedPolicy(
        policy_id="p1",
        phase=SocialPhase.DISCOVERY,
        predicate=lambda a, ctx: "ok" in a.payload.get("content", ""),
        required_fields={"payload.content"},
    ))
    pt = PhaseTracker()
    log = [_mk("a", 0, phase=SocialPhase.DISCOVERY, payload={"content": "bad"})]
    result = phase_scoped_policy.score(
        action_log=log, policy_registry=reg, phase_tracker=pt
    )
    assert result.scalar == 0.0


def test_phase_scoped_policy_no_policies_is_one():
    reg = PolicyRegistry()
    pt = PhaseTracker()
    log = [_mk("a", 0)]
    result = phase_scoped_policy.score(
        action_log=log, policy_registry=reg, phase_tracker=pt
    )
    assert result.scalar == 1.0


def test_phase_scoped_policy_zero_records_in_phase():
    """A REPAIR-phase policy with only DISCOVERY records is vacuously satisfied."""
    reg = PolicyRegistry()
    reg.register_phase_scoped(PhaseScopedPolicy(
        policy_id="p1",
        phase=SocialPhase.REPAIR,  # no records in this phase
        predicate=lambda a, ctx: True,
        required_fields={"payload.content"},
    ))
    pt = PhaseTracker()
    log = [_mk("a", 0, phase=SocialPhase.DISCOVERY)]
    result = phase_scoped_policy.score(
        action_log=log, policy_registry=reg, phase_tracker=pt
    )
    assert result.scalar == 1.0
    assert result.per_policy["p1"]["vacuous"] is True
    assert result.per_policy["p1"]["decidable"] is True
    assert result.per_policy["p1"]["satisfied"] is True


def test_phase_scoped_policy_not_decidable_when_field_missing():
    """An in-phase record missing a required field makes the policy not decidable."""
    reg = PolicyRegistry()
    reg.register_phase_scoped(PhaseScopedPolicy(
        policy_id="p1",
        phase=SocialPhase.DISCOVERY,
        predicate=lambda a, ctx: True,
        required_fields={"payload.nonexistent_field"},
    ))
    pt = PhaseTracker()
    log = [_mk("a", 0, phase=SocialPhase.DISCOVERY)]
    result = phase_scoped_policy.score(
        action_log=log, policy_registry=reg, phase_tracker=pt
    )
    # Not decidable -> not counted as decidable_and_satisfied
    assert result.scalar == 0.0
    assert result.per_policy["p1"]["decidable"] is False
    assert result.per_policy["p1"]["satisfied"] is None  # can't evaluate


def test_phase_scoped_policy_violated():
    """A decidable policy whose predicate fails counts as violated."""
    reg = PolicyRegistry()
    reg.register_phase_scoped(PhaseScopedPolicy(
        policy_id="p1",
        phase=SocialPhase.DISCOVERY,
        predicate=lambda a, ctx: "ok" in a.payload.get("content", ""),
        required_fields={"payload.content"},
    ))
    pt = PhaseTracker()
    log = [_mk("a", 0, phase=SocialPhase.DISCOVERY, payload={"content": "bad"})]
    result = phase_scoped_policy.score(
        action_log=log, policy_registry=reg, phase_tracker=pt
    )
    assert result.scalar == 0.0
    assert result.per_policy["p1"]["decidable"] is True
    assert result.per_policy["p1"]["satisfied"] is False
    assert result.per_policy["p1"]["vacuous"] is False
