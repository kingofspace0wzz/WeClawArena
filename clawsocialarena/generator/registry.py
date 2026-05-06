"""Registry of (category, task_family) -> Template class."""

from __future__ import annotations

from dataclasses import dataclass

from clawsocialarena.generator.attack_injection import AttackType
from clawsocialarena.generator.template import (
    CategoryCode,
    TaskFamily,
    Template,
)
from clawsocialarena.generator.templates.am_inference import AMInferenceTemplate
from clawsocialarena.generator.templates.am_scheduling import AMSchedulingTemplate
from clawsocialarena.generator.templates.cd_consensus import CDConsensusTemplate
from clawsocialarena.generator.templates.cd_inference import CDInferenceTemplate
from clawsocialarena.generator.templates.cm_coalition import CMCoalitionTemplate
from clawsocialarena.generator.templates.cm_consensus import CMConsensusTemplate
from clawsocialarena.generator.templates.cu_coalition import CUCoalitionTemplate
from clawsocialarena.generator.templates.cu_scheduling import CUSchedulingTemplate
from clawsocialarena.generator.templates.hard_code_review import HardCodeReviewTemplate
from clawsocialarena.generator.templates.hard_doc_editing import HardDocEditingTemplate
from clawsocialarena.generator.templates.hs_coalition import HSCoalitionTemplate
from clawsocialarena.generator.templates.hs_consensus import HSConsensusTemplate
from clawsocialarena.generator.templates.mc_inference import MCInferenceTemplate
from clawsocialarena.generator.templates.mc_scheduling import MCSchedulingTemplate
from clawsocialarena.generator.templates.mg_coalition import MGCoalitionTemplate
from clawsocialarena.generator.templates.mg_consensus import MGConsensusTemplate


_REGISTRY: dict[tuple[CategoryCode, TaskFamily], type[Template]] = {
    (CategoryCode.CU, TaskFamily.SCHEDULING): CUSchedulingTemplate,
    (CategoryCode.MC, TaskFamily.SCHEDULING): MCSchedulingTemplate,
    (CategoryCode.AM, TaskFamily.SCHEDULING): AMSchedulingTemplate,
    (CategoryCode.CD, TaskFamily.CONSENSUS): CDConsensusTemplate,
    (CategoryCode.MG, TaskFamily.CONSENSUS): MGConsensusTemplate,
    (CategoryCode.HS, TaskFamily.CONSENSUS): HSConsensusTemplate,
    (CategoryCode.CM, TaskFamily.CONSENSUS): CMConsensusTemplate,
    (CategoryCode.CD, TaskFamily.INFERENCE): CDInferenceTemplate,
    (CategoryCode.MC, TaskFamily.INFERENCE): MCInferenceTemplate,
    (CategoryCode.AM, TaskFamily.INFERENCE): AMInferenceTemplate,
    (CategoryCode.CU, TaskFamily.COALITION): CUCoalitionTemplate,
    (CategoryCode.MG, TaskFamily.COALITION): MGCoalitionTemplate,
    (CategoryCode.HS, TaskFamily.COALITION): HSCoalitionTemplate,
    (CategoryCode.CM, TaskFamily.COALITION): CMCoalitionTemplate,
    (CategoryCode.CU, TaskFamily.CODE_REVIEW): HardCodeReviewTemplate,
    (CategoryCode.MC, TaskFamily.DOC_EDITING): HardDocEditingTemplate,
}


@dataclass(frozen=True)
class PhaseEGovernanceMainRow:
    """Planning-only row for Phase E governance main coverage.

    These rows reserve governance coverage before final Phase E generation.
    """

    scenario_id: str
    category: CategoryCode
    task_family: TaskFamily
    seed: int
    attack_axis: str
    attack_type: AttackType


PHASE_E_AXIS_TOTALS: dict[str, int] = {
    "benign": 33,
    "collaboration": 26,
    "security": 17,
    "privacy": 9,
    "governance": 15,
}

PHASE_E_GOVERNANCE_ATTACK_COUNTS: dict[AttackType, int] = {
    AttackType.OWNER_BINDING_SPOOFING: 3,
    AttackType.IDENTITY_CONFUSION: 3,
    AttackType.SCOPE_CREEP: 3,
    AttackType.APPROVAL_BYPASS: 2,
    AttackType.MANDATE_LAUNDERING: 2,
    AttackType.AUDIT_EVASION: 2,
}

_PHASE_E_GOVERNANCE_CATEGORY_MIX: tuple[
    tuple[CategoryCode, TaskFamily],
    ...,
] = (
    (CategoryCode.CU, TaskFamily.SCHEDULING),
    (CategoryCode.MG, TaskFamily.CONSENSUS),
    (CategoryCode.HS, TaskFamily.CONSENSUS),
    (CategoryCode.CM, TaskFamily.CONSENSUS),
    (CategoryCode.AM, TaskFamily.SCHEDULING),
)

_PHASE_E_AUDIT_CHALLENGE_CASES: tuple[str, ...] = (
    "inferential_leakage_v1",
    "cross_delegation_attr_v1",
    "partial_log_recovery_v1",
    "mandate_laundering_v1",
    "approval_bypass_v1",
)


def get_template(category: CategoryCode, task_family: TaskFamily) -> Template:
    key = (category, task_family)
    if key not in _REGISTRY:
        raise KeyError(
            f"no template registered for ({category.value}, {task_family.value}). "
            f"Registered: {[(c.value, t.value) for c, t in _REGISTRY.keys()]}"
        )
    return _REGISTRY[key]()


def list_registered() -> list[tuple[CategoryCode, TaskFamily]]:
    return list(_REGISTRY.keys())


def phase_e_governance_main_rows(
    *,
    base_seed: int,
) -> list[PhaseEGovernanceMainRow]:
    """Return the 15 governance adversarial main rows reserved for Phase E."""

    attack_pool = [
        attack_type
        for attack_type, count in PHASE_E_GOVERNANCE_ATTACK_COUNTS.items()
        for _ in range(count)
    ]
    rows: list[PhaseEGovernanceMainRow] = []
    for index, attack_type in enumerate(attack_pool):
        category, task_family = _PHASE_E_GOVERNANCE_CATEGORY_MIX[
            index % len(_PHASE_E_GOVERNANCE_CATEGORY_MIX)
        ]
        seed = base_seed + index
        scenario_id = (
            f"{category.value.lower()}-{task_family.value}-"
            f"governance-{seed:05d}"
        )
        rows.append(
            PhaseEGovernanceMainRow(
                scenario_id=scenario_id,
                category=category,
                task_family=task_family,
                seed=seed,
                attack_axis="governance",
                attack_type=attack_type,
            )
        )
    return rows


def phase_e_audit_challenge_case_ids() -> tuple[str, ...]:
    """Return the five named audit challenge case ids for v1.0.0."""

    return _PHASE_E_AUDIT_CHALLENGE_CASES
