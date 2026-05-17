"""Sanity tests for shared_account seed data."""
from __future__ import annotations

from clawsocialarena.generator.family_packs.tau2_retail.seeds import (
    SHARED_ACCOUNT_TASK_SEEDS,
)


def test_six_base_tasks_present() -> None:
    assert len(SHARED_ACCOUNT_TASK_SEEDS) == 6
    indices = [seed.task_index for seed in SHARED_ACCOUNT_TASK_SEEDS]
    assert indices == [0, 1, 2, 3, 4, 5]


def test_action_surfaces_cover_all_six() -> None:
    surfaces = {seed.action_surface for seed in SHARED_ACCOUNT_TASK_SEEDS}
    assert surfaces == {
        "exchange_delivered_order_items",
        "return_delivered_order_items",
        "cancel_pending_order",
        "modify_pending_order_address",
        "modify_pending_order_items",
        "modify_pending_order_payment",
    }


def test_every_seed_carries_overcap_authorization_code() -> None:
    for seed in SHARED_ACCOUNT_TASK_SEEDS:
        assert seed.primary_approval_authorization_code.startswith("HH-")
        assert seed.secondary_spending_cap_usd == 100


def test_every_seed_marks_untrusted_files_unprotected() -> None:
    for seed in SHARED_ACCOUNT_TASK_SEEDS:
        for workspace in (seed.primary_workspace, seed.secondary_workspace):
            for file in workspace.files:
                if file.path.endswith("_notes.md") or file.path.endswith("_requests.md"):
                    assert file.protected is False, (
                        f"{seed.task_index} {workspace.owner_id} {file.path}"
                    )
