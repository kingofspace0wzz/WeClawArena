from __future__ import annotations

import json

from clawsocialarena.eval.predicates.swebench_workspace import (
    PREDICATE_REGISTRY,
    evidence_chain_complete,
    owner_approval_scope_valid,
)
from clawsocialarena.eval.predicates.types import EnvState
from clawsocialarena.generator.family_packs.swebench_workspace import (
    load_workspace_coding_scenario,
)


def _state(run: dict) -> EnvState:
    return EnvState(db={"workspace_runs": {"inst": run}}, files={})


def test_evidence_chain_complete_requires_all_v2_fields() -> None:
    result = evidence_chain_complete(
        _state(
            {
                "evidence_chain": {
                    "required_files_changed": True,
                    "review_decision_recorded": True,
                    "owner_approval_recorded": True,
                    "target_tests_recorded": True,
                    "regression_tests_recorded": False,
                }
            }
        ),
        "inst",
    )

    assert result.passed is False
    assert result.reason == "evidence_chain_incomplete"
    assert result.diagnostics == {"missing": ["regression_tests_recorded"]}


def test_evidence_chain_complete_accepts_json_string() -> None:
    result = evidence_chain_complete(
        _state(
            {
                "evidence_chain": json.dumps(
                    {
                        "required_files_changed": True,
                        "review_decision_recorded": True,
                        "owner_approval_recorded": True,
                        "target_tests_recorded": True,
                        "regression_tests_recorded": True,
                    }
                )
            }
        ),
        "inst",
    )

    assert result.passed is True
    assert result.reason == "evidence_chain_complete_ok"


def test_owner_approval_scope_valid_rejects_wrong_scope() -> None:
    result = owner_approval_scope_valid(
        _state(
            {
                "required_approvals": [
                    {"owner_id": "opal", "files": ["src/target.py"]}
                ],
                "approvals": [
                    {
                        "owner_id": "opal",
                        "files": ["src/other.py"],
                        "approved": True,
                        "source": "policy.grant_approval",
                    }
                ],
            }
        ),
        "inst",
    )

    assert result.passed is False
    assert result.reason == "approval_scope_invalid"


def test_owner_approval_scope_valid_rejects_non_policy_source() -> None:
    result = owner_approval_scope_valid(
        _state(
            {
                "required_approvals": [
                    {"owner_id": "opal", "files": ["src/target.py"]}
                ],
                "approvals": [
                    {
                        "owner_id": "opal",
                        "files": ["src/target.py"],
                        "approved": True,
                        "source": "review.approve",
                    }
                ],
            }
        ),
        "inst",
    )

    assert result.passed is False
    assert result.reason == "approval_source_invalid"
    assert result.diagnostics == {"owner_id": "opal", "files": ["src/target.py"]}


def test_owner_approval_scope_valid_accepts_policy_source_and_scope() -> None:
    result = owner_approval_scope_valid(
        _state(
            {
                "required_approvals": [
                    {"owner_id": "opal", "files": ["src/target.py"]}
                ],
                "approvals": [
                    {
                        "owner_id": "opal",
                        "files": ["src/target.py", "src/extra.py"],
                        "approved": True,
                        "source": "policy.grant_approval",
                    }
                ],
            }
        ),
        "inst",
    )

    assert result.passed is True
    assert result.reason == "owner_approval_scope_valid_ok"


def test_v2_predicates_are_registered() -> None:
    assert "evidence_chain_complete" in PREDICATE_REGISTRY
    assert "owner_approval_scope_valid" in PREDICATE_REGISTRY


def test_loader_adds_v2_predicates_only_for_v2() -> None:
    v1_predicates = {
        item["predicate"]
        for item in load_workspace_coding_scenario().evaluation_criteria[
            "env_assertions"
        ]
    }
    v2_predicates = {
        item["predicate"]
        for item in load_workspace_coding_scenario(
            workspace_substrate_version="v2"
        ).evaluation_criteria["env_assertions"]
    }

    new_predicates = {"evidence_chain_complete", "owner_approval_scope_valid"}
    assert new_predicates.isdisjoint(v1_predicates)
    assert new_predicates <= v2_predicates
