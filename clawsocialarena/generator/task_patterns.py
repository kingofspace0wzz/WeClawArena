from __future__ import annotations

from typing import Any

from clawsocialarena.generator.template import TaskFamily


_PATTERNS: dict[tuple[TaskFamily, str], dict[str, str]] = {
    (TaskFamily.SCHEDULING, "easy"): {
        "benchmark": "tau2-bench",
        "path": "data/tau2/domains/airline/tasks.json",
        "motif": "policy_bounded_reschedule",
    },
    (TaskFamily.SCHEDULING, "realistic"): {
        "benchmark": "WildClawBench",
        "path": "tasks/03_Social_Interaction/calendar_scheduling",
        "motif": "calendar_scheduling",
    },
    (TaskFamily.SCHEDULING, "stress"): {
        "benchmark": "WildClawBench",
        "path": "tasks/03_Social_Interaction/calendar_scheduling_stress",
        "motif": "calendar_scheduling",
    },
    (TaskFamily.CONSENSUS, "easy"): {
        "benchmark": "tau2-bench",
        "path": "data/tau2/domains/banking/tasks.json",
        "motif": "authoritative_state_check",
    },
    (TaskFamily.CONSENSUS, "realistic"): {
        "benchmark": "tau2-bench",
        "path": "data/tau2/domains/telecom/tasks.json",
        "motif": "multi_state_resolution",
    },
    (TaskFamily.CONSENSUS, "stress"): {
        "benchmark": "WildClawBench",
        "path": "tasks/03_Social_Interaction/stale_update_resolution",
        "motif": "conflicting_social_evidence",
    },
    (TaskFamily.INFERENCE, "easy"): {
        "benchmark": "tau2-bench",
        "path": "data/tau2/domains/banking_knowledge/tasks/task_001.json",
        "motif": "required_document_grounding",
    },
    (TaskFamily.INFERENCE, "realistic"): {
        "benchmark": "tau2-bench",
        "path": "data/tau2/domains/banking_knowledge/tasks/task_029.json",
        "motif": "allowed_summary_with_forbidden_inference",
    },
    (TaskFamily.INFERENCE, "stress"): {
        "benchmark": "WildClawBench",
        "path": "tasks/04_Search_Retrieval/conflicting_handling",
        "motif": "conflicting_evidence_boundary",
    },
    (TaskFamily.COALITION, "easy"): {
        "benchmark": "tau2-bench",
        "path": "data/tau2/domains/telecom/tasks.json",
        "motif": "dual_control_action",
    },
    (TaskFamily.COALITION, "realistic"): {
        "benchmark": "WildClawBench",
        "path": "tasks/03_Social_Interaction/escalation_routing",
        "motif": "role_bound_group_action",
    },
    (TaskFamily.COALITION, "stress"): {
        "benchmark": "WildClawBench",
        "path": "tasks/06_Safety_Alignment/authority_boundary",
        "motif": "semantic_authority_boundary",
    },
    (TaskFamily.CODE_REVIEW, "realistic"): {
        "benchmark": "tau2-bench",
        "path": "src/tau2/evaluator/review_llm_judge.py",
        "motif": "planted_error_taxonomy",
    },
    (TaskFamily.CODE_REVIEW, "easy"): {
        "benchmark": "tau2-bench",
        "path": "tests/tau2/unit/review_fixture.py",
        "motif": "single_planted_error",
    },
    (TaskFamily.CODE_REVIEW, "stress"): {
        "benchmark": "WildClawBench",
        "path": "tasks/06_Safety_Alignment/code_review_decoys",
        "motif": "planted_error_taxonomy_with_decoys",
    },
    (TaskFamily.DOC_EDITING, "realistic"): {
        "benchmark": "WildClawBench",
        "path": "tasks/06_Safety_Alignment/file_overwrite",
        "motif": "protected_document_edit",
    },
    (TaskFamily.DOC_EDITING, "easy"): {
        "benchmark": "tau2-bench",
        "path": "data/tau2/domains/retail/tasks.json",
        "motif": "single_document_field_update",
    },
    (TaskFamily.DOC_EDITING, "stress"): {
        "benchmark": "WildClawBench",
        "path": "tasks/06_Safety_Alignment/file_overwrite_stress",
        "motif": "conflicting_document_edits",
    },
}


def pattern_for(*, family: str, tier: str) -> dict[str, Any]:
    task_family = TaskFamily(family)
    pattern = _PATTERNS.get((task_family, tier)) or _PATTERNS.get(
        (task_family, "realistic")
    )
    if pattern is None:
        pattern = {
            "benchmark": "tau2-bench",
            "path": "data/tau2/domains/generic/tasks.json",
            "motif": "declared_task_contract",
        }
    return {**pattern, "adaptation": "structural_motif_only"}
