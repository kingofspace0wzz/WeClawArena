"""Sanity tests for cross_account seed data."""
from __future__ import annotations

from clawsocialarena.generator.family_packs.tau2_retail.seeds import (
    CROSS_ACCOUNT_TASK_SEEDS,
)


def test_six_cross_account_tasks_present() -> None:
    assert len(CROSS_ACCOUNT_TASK_SEEDS) == 6
    indices = [seed.task_index for seed in CROSS_ACCOUNT_TASK_SEEDS]
    assert indices == [0, 1, 2, 3, 4, 5]


def test_cross_account_uses_distinct_owners() -> None:
    for seed in CROSS_ACCOUNT_TASK_SEEDS:
        assert seed.sender_owner != seed.recipient_owner


def test_cross_account_recipient_consent_codes_distinct() -> None:
    codes = {s.recipient_consent_authorization_code for s in CROSS_ACCOUNT_TASK_SEEDS}
    assert len(codes) == 6


def test_cross_account_no_shared_resources() -> None:
    # CrossAccountTaskSeed does not have a shared_resources field — every
    # task is independent customer-to-customer state, no cross-owner shared DB.
    for seed in CROSS_ACCOUNT_TASK_SEEDS:
        assert not hasattr(seed, "shared_resources")
