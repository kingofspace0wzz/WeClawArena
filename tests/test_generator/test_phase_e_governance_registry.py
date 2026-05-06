"""Phase E governance coverage metadata tests."""

from __future__ import annotations

from collections import Counter

from clawsocialarena.generator.attack_injection import AttackType
from clawsocialarena.generator.registry import (
    PHASE_E_AXIS_TOTALS,
    PHASE_E_GOVERNANCE_ATTACK_COUNTS,
    phase_e_audit_challenge_case_ids,
    phase_e_governance_main_rows,
)
from clawsocialarena.generator.template import CategoryCode


def test_phase_e_axis_totals_reserve_governance_main_coverage() -> None:
    assert PHASE_E_AXIS_TOTALS == {
        "benign": 33,
        "collaboration": 26,
        "security": 17,
        "privacy": 9,
        "governance": 15,
    }
    assert sum(PHASE_E_AXIS_TOTALS.values()) == 100


def test_phase_e_governance_rows_cover_categories_and_attack_types() -> None:
    rows = phase_e_governance_main_rows(base_seed=9000)

    assert len(rows) == 15
    assert {row.attack_axis for row in rows} == {"governance"}
    assert Counter(row.category for row in rows) == {
        CategoryCode.CU: 3,
        CategoryCode.MG: 3,
        CategoryCode.HS: 3,
        CategoryCode.CM: 3,
        CategoryCode.AM: 3,
    }
    assert Counter(row.attack_type for row in rows) == PHASE_E_GOVERNANCE_ATTACK_COUNTS
    assert set(PHASE_E_GOVERNANCE_ATTACK_COUNTS) == {
        AttackType.OWNER_BINDING_SPOOFING,
        AttackType.IDENTITY_CONFUSION,
        AttackType.SCOPE_CREEP,
        AttackType.APPROVAL_BYPASS,
        AttackType.MANDATE_LAUNDERING,
        AttackType.AUDIT_EVASION,
    }


def test_phase_e_audit_challenge_contract_lists_all_five_cases() -> None:
    assert phase_e_audit_challenge_case_ids() == (
        "inferential_leakage_v1",
        "cross_delegation_attr_v1",
        "partial_log_recovery_v1",
        "mandate_laundering_v1",
        "approval_bypass_v1",
    )
