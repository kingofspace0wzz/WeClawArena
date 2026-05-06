from clawsocialarena.audit.policy_catalog import PolicyCatalog
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


def _rec(content: str) -> ActionRecord:
    return ActionRecord(
        action_id="a-1",
        prev_hash="0" * 64,
        agent_id="reviewer-primary",
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-05-02T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={"content": content},
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def test_catalog_contains_any_of_matches_case_insensitive_substrings():
    policy = PolicyCatalog().flat_from_dict(
        {
            "policy_id": "review-must-name-bug-ids",
            "kind": "contains_any_of",
            "params": {
                "substrings": ["bug-off-by-one", "bug-sql-injection"],
                "field": "payload.content",
            },
            "required_fields": ["payload.content"],
        }
    )

    assert policy.predicate(_rec("I found BUG-SQL-INJECTION on line 22."), {}) is True
    assert policy.predicate(_rec("I only found a style issue."), {}) is False
