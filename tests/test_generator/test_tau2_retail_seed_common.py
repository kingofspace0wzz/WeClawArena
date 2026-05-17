"""Tests for the shared tau2_retail seed dataclasses."""
from __future__ import annotations

from clawsocialarena.generator.family_packs.tau2_retail.seeds import (
    OwnerWorkspaceSeed,
    WorkspaceFileSeed,
    WorkspaceTableSeed,
)


def test_owner_workspace_seed_serializes_to_loader_dict() -> None:
    workspace = OwnerWorkspaceSeed(
        owner_id="alice",
        role_label="primary_account_holder",
        files=(
            WorkspaceFileSeed(
                path="shared_account_rules.md",
                content="# Rules\n",
                protected=True,
            ),
        ),
        tables=(
            WorkspaceTableSeed(
                name="payment_methods",
                schema=(
                    "CREATE TABLE payment_methods ("
                    "pm_id TEXT PRIMARY KEY, brand TEXT NOT NULL, "
                    "last_four TEXT NOT NULL, gift_card_balance REAL NOT NULL)"
                ),
                rows=({"pm_id": "pm_alice_cc_01", "brand": "visa", "last_four": "0042", "gift_card_balance": 0.0},),
            ),
        ),
    )

    payload = workspace.as_loader_dict()

    assert payload["owner_id"] == "alice"
    assert payload["role_label"] == "primary_account_holder"
    assert payload["files"][0]["path"] == "shared_account_rules.md"
    assert payload["files"][0]["protected"] is True
    assert payload["tables"][0]["name"] == "payment_methods"
    assert payload["tables"][0]["rows"][0]["pm_id"] == "pm_alice_cc_01"
