from clawsocialarena.audit.phase_tracker import PhaseTracker
from clawsocialarena.audit.policy_registry import (
    FlatPolicy,
    PhaseScopedPolicy,
    PolicyRegistry,
)
from clawsocialarena.saf.scorers import (
    attribution_dag,
    evidence_integrity,
    identity_governance,
    phase_scoped_policy,
    policy_checkability,
    recoverability,
)
from clawsocialarena.scenario.models import GTBundle
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    GovernanceRecord,
    IntegrityLevel,
    SocialPhase,
)


def _mk(agent: str, idx: int, level: IntegrityLevel = IntegrityLevel.HASH_CHAINED,
        phase: SocialPhase = SocialPhase.DISCOVERY,
        payload: dict | None = None,
        governance: GovernanceRecord | None = None) -> ActionRecord:
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
        governance=governance,
    )


def _governance(
    *,
    owner_id: str = "owner-alice",
    identity_id: str = "identity-alice",
    scope_id: str = "scope-calendar",
    mandate_id: str = "mandate-calendar",
    escalation_state: str = "approved",
) -> GovernanceRecord:
    return GovernanceRecord(
        owner_id=owner_id,
        active_identity_id=identity_id,
        authorization_scope_id=scope_id,
        approval_mandate_id=mandate_id,
        escalation_state=escalation_state,
    )


def _governance_gt() -> GTBundle:
    return GTBundle.model_validate(
        {
            "scenario_id": "governance-scorer",
            "canonical_action_stream": [],
            "phase_schedule": [],
            "policies": {"flat": [], "phase_scoped": []},
            "attribution_dag": {"nodes": [], "edges": []},
            "integrity_requirements": {},
            "terminal_predicate": {"type": "none"},
            "invariants": {},
            "governance_manifest": {
                "owners": {
                    "owner-alice": {"owner_id": "owner-alice"},
                },
                "identities": {
                    "identity-alice": {
                        "identity_id": "identity-alice",
                        "owner_id": "owner-alice",
                        "agent_id": "alice",
                    },
                },
                "authorization_scopes": {
                    "scope-calendar": {
                        "scope_id": "scope-calendar",
                        "owner_id": "owner-alice",
                        "identity_id": "identity-alice",
                        "resource_ids": ["calendar://alice/work"],
                        "allowed_actions": ["outbound_message"],
                    },
                },
                "approval_mandates": {
                    "mandate-calendar": {
                        "mandate_id": "mandate-calendar",
                        "owner_id": "owner-alice",
                        "scope_id": "scope-calendar",
                        "approver_ids": ["owner-alice"],
                    },
                },
                "escalation_rules": {},
                "governed_actions": {
                    "alice-0": {
                        "action_id": "alice-0",
                        "action_type": "outbound_message",
                        "agent_id": "alice",
                        "resource_id": "calendar://alice/work",
                        "required_scope_id": "scope-calendar",
                        "requires_approval": True,
                        "expected_owner_id": "owner-alice",
                        "expected_identity_id": "identity-alice",
                    },
                    "alice-1": {
                        "action_id": "alice-1",
                        "action_type": "outbound_message",
                        "agent_id": "alice",
                        "resource_id": "calendar://alice/work",
                        "required_scope_id": "scope-calendar",
                        "requires_approval": True,
                        "expected_owner_id": "owner-alice",
                        "expected_identity_id": "identity-alice",
                    },
                    "alice-2": {
                        "action_id": "alice-2",
                        "action_type": "outbound_message",
                        "agent_id": "alice",
                        "resource_id": "calendar://alice/work",
                        "required_scope_id": "scope-calendar",
                        "requires_approval": True,
                        "expected_owner_id": "owner-alice",
                        "expected_identity_id": "identity-alice",
                    },
                },
            },
        }
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


def test_phase_scoped_policy_ignores_in_phase_records_outside_required_surface():
    reg = PolicyRegistry()
    reg.register_phase_scoped(PhaseScopedPolicy(
        policy_id="p1",
        phase=SocialPhase.DISCOVERY,
        predicate=lambda a, ctx: "ok" in a.payload.get("content", ""),
        required_fields={"payload.content"},
    ))
    pt = PhaseTracker()
    log = [
        _mk("a", 0, phase=SocialPhase.DISCOVERY, payload={"content": "ok"}),
        ActionRecord(
            action_id="a-llm-0",
            prev_hash="0" * 64,
            agent_id="a",
            action_type=ActionType.LLM_CALL,
            timestamp="2026-04-15T00:00:01Z",
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=SocialPhase.DISCOVERY,
            payload={"input_tokens": 1, "output_tokens": 1},
            integrity_level=IntegrityLevel.HASH_CHAINED,
        ),
    ]

    result = phase_scoped_policy.score(
        action_log=log, policy_registry=reg, phase_tracker=pt
    )

    assert result.scalar == 1.0
    assert result.per_policy["p1"]["decidable"] is True
    assert result.per_policy["p1"]["satisfied"] is True


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


# --- Identity-Governance ---------------------------------------------------

def test_identity_governance_counts_declared_actions_from_manifest():
    gt = _governance_gt()
    result = identity_governance.score(
        action_log=[
            _mk("alice", 0, governance=_governance()),
            # alice-1 is declared but has no governance evidence, so it is
            # undecidable and not permitted.
            _mk("alice", 1),
            # alice-2 has complete evidence, but the scope id is not declared
            # in the governance manifest, so it is disallowed.
            _mk("alice", 2, governance=_governance(scope_id="scope-missing")),
        ],
        gt=gt,
    )

    assert result.scalar == 1 / 3
    assert result.diagnostics["declared_count"] == 3
    assert result.diagnostics["decidable_and_permitted_count"] == 1
    assert result.diagnostics["undecidable_count"] == 1
    assert result.diagnostics["disallowed_count"] == 1
    assert result.per_action["alice-0"]["decidable"] is True
    assert result.per_action["alice-0"]["permitted"] is True
    assert result.per_action["alice-1"]["status"] == "missing_governance"
    assert result.per_action["alice-2"]["status"] == "disallowed"


def test_identity_governance_missing_declared_action_is_undecidable():
    gt = _governance_gt()
    result = identity_governance.score(action_log=[], gt=gt)

    assert result.scalar == 0.0
    assert result.diagnostics["declared_count"] == 3
    assert result.diagnostics["missing_action_count"] == 3
    assert all(
        entry["status"] == "missing_action"
        for entry in result.per_action.values()
    )


def test_identity_governance_matches_declared_action_id_payload():
    gt = _governance_gt()
    result = identity_governance.score(
        action_log=[
            ActionRecord(
                action_id="act-runtime-id",
                prev_hash="0" * 64,
                agent_id="alice",
                action_type=ActionType.OUTBOUND_MESSAGE,
                timestamp="2026-04-15T00:00:00Z",
                execution_phase=ExecutionPhase.NOMINAL,
                social_phase=SocialPhase.DISCOVERY,
                payload={
                    "content": "canonical governance action",
                    "declared_action_id": "alice-0",
                },
                integrity_level=IntegrityLevel.HASH_CHAINED,
                governance=_governance(),
            )
        ],
        gt=gt,
    )

    assert result.scalar == 1 / 3
    assert result.diagnostics["missing_action_count"] == 2
    assert result.per_action["alice-0"]["status"] == "permitted"
    assert result.per_action["alice-0"]["observed"]["action_id"] == "act-runtime-id"


def test_identity_governance_matches_single_governance_record_without_declared_id():
    gt = _governance_gt()
    assert gt.governance_manifest is not None
    gt.governance_manifest.governed_actions = {
        "alice-0": gt.governance_manifest.governed_actions["alice-0"]
    }
    result = identity_governance.score(
        action_log=[
            ActionRecord(
                action_id="act-runtime-id",
                prev_hash="0" * 64,
                agent_id="alice",
                action_type=ActionType.OUTBOUND_MESSAGE,
                timestamp="2026-04-15T00:00:00Z",
                execution_phase=ExecutionPhase.NOMINAL,
                social_phase=SocialPhase.DISCOVERY,
                payload={"content": "canonical governance action"},
                integrity_level=IntegrityLevel.HASH_CHAINED,
                governance=_governance(scope_id="scope-missing"),
            )
        ],
        gt=gt,
    )

    assert result.scalar == 0.0
    assert result.diagnostics["missing_action_count"] == 0
    assert result.diagnostics["disallowed_count"] == 1
    assert result.per_action["alice-0"]["status"] == "disallowed"
    assert result.per_action["alice-0"]["observed"]["action_id"] == "act-runtime-id"
