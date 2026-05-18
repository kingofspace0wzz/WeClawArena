"""Tests for owned-ecosystem marble_bargaining materialization."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.generator.family_packs.marble_bargaining import (
    load_bargaining_scenario,
    materialize_bargaining_bundle,
)
from clawsocialarena.generator.phase5_task_variants import task_variants_for


@pytest.fixture
def bundle_dir(tmp_path: Path) -> Path:
    bundle = load_bargaining_scenario()
    return materialize_bargaining_bundle(bundle, tmp_path / "scenario")


def test_writes_top_level_artifacts(bundle_dir: Path) -> None:
    for name in (
        "scenario.json",
        "scenario.gt.json",
        "family_pack_context.json",
        "docker-compose.yml",
    ):
        assert (bundle_dir / name).is_file()


def test_owned_ecosystem_materializer_writes_files_and_tables(
    tmp_path: Path,
) -> None:
    bundle = load_bargaining_scenario()
    bundle_dir = materialize_bargaining_bundle(bundle, tmp_path / "scenario")

    buyer_root = bundle_dir / "resources" / "agents" / "acme_procurement"
    seller_root = bundle_dir / "resources" / "agents" / "northstar_sales"
    approver_root = bundle_dir / "resources" / "agents" / "acme_finance"

    assert (buyer_root / "files" / "purchase_request.md").is_file()
    assert (buyer_root / "files" / "procurement_policy.md").is_file()
    assert (seller_root / "files" / "sales_policy.md").is_file()
    assert (seller_root / "files" / "contract_template.md").is_file()
    assert (approver_root / "files" / "delegation_policy.md").is_file()

    buyer_db_path = buyer_root / "db" / "personal.sqlite"
    assert buyer_db_path.is_file()
    with sqlite3.connect(buyer_db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"budget_ledger", "purchase_orders", "negotiation_state"} <= tables

    seller_db_path = seller_root / "db" / "personal.sqlite"
    assert seller_db_path.is_file()
    with sqlite3.connect(seller_db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"inventory", "price_book", "seller_orders", "negotiation_state"} <= tables

    approver_db_path = approver_root / "db" / "personal.sqlite"
    assert approver_db_path.is_file()
    with sqlite3.connect(approver_db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"approval_rules", "approval_log", "delegations"} <= tables


def test_family_pack_context_carries_owned_ecosystem_ids(bundle_dir: Path) -> None:
    context = json.loads((bundle_dir / "family_pack_context.json").read_text())
    assert context["transaction_id"] == "TXN-OE-001"
    assert context["resource_profile"] == "owned_ecosystem_procurement"
    assert context["item_id"] == "PRINTER-BUNDLE-12"
    assert context["quantity"] == 12
    assert context["target_price"] == 795.0
    assert context["buyer_owner_id"] == "acme_procurement"
    assert context["seller_owner_id"] == "northstar_sales"
    assert context["approver_owner_id"] == "acme_finance"
    assert context["buyer_agent_id"] == "acme_buyer"
    assert context["seller_agent_id"] == "northstar_seller"
    assert context["approver_agent_id"] == "acme_finance_approver"


def test_personas_get_role_specific_owned_ecosystem_tools(bundle_dir: Path) -> None:
    buyer_tools = json.loads(
        (bundle_dir / "personas" / "acme_buyer.tools.json").read_text()
    )
    seller_tools = json.loads(
        (bundle_dir / "personas" / "northstar_seller.tools.json").read_text()
    )
    approver_tools = json.loads(
        (bundle_dir / "personas" / "acme_finance_approver.tools.json").read_text()
    )

    assert "record_purchase_order" in buyer_tools
    assert "record_seller_acceptance" in seller_tools
    assert "issue_purchase_approval" in approver_tools
    assert "record_purchase_order" not in seller_tools
    assert "record_seller_acceptance" not in approver_tools


def test_personas_include_exact_owner_id_tool_contract(bundle_dir: Path) -> None:
    buyer_prompt = (bundle_dir / "personas" / "acme_buyer.system.md").read_text()
    seller_prompt = (
        bundle_dir / "personas" / "northstar_seller.system.md"
    ).read_text()
    approver_prompt = (
        bundle_dir / "personas" / "acme_finance_approver.system.md"
    ).read_text()

    assert "Agent ID: `acme_buyer`" in buyer_prompt
    assert "Owner ID: `acme_procurement`" in buyer_prompt
    assert "requester_owner_id: `acme_procurement`" in buyer_prompt
    assert "buyer_owner_id: `acme_procurement`" in buyer_prompt
    assert "seller_owner_id: `northstar_sales`" in buyer_prompt
    assert "approver_owner_id: `acme_finance`" in buyer_prompt
    assert "Do not use `acme_buyer` in owner ID fields." in buyer_prompt

    assert "Agent ID: `northstar_seller`" in seller_prompt
    assert "Owner ID: `northstar_sales`" in seller_prompt
    assert "owner_id: `northstar_sales`" in seller_prompt
    assert "seller_owner_id: `northstar_sales`" in seller_prompt
    assert "Do not use `northstar_seller` in owner ID fields." in seller_prompt

    assert "Agent ID: `acme_finance_approver`" in approver_prompt
    assert "Owner ID: `acme_finance`" in approver_prompt
    assert "approver_owner_id: `acme_finance`" in approver_prompt
    assert "Do not use `acme_finance_approver` in owner ID fields." in approver_prompt


def test_compose_threads_family_pack_flags(bundle_dir: Path) -> None:
    compose_text = (bundle_dir / "docker-compose.yml").read_text()
    assert "marble_bargaining" in compose_text
    assert "--family-pack-context-path" in compose_text


def test_gt_carries_owned_ecosystem_evaluation_criteria(bundle_dir: Path) -> None:
    gt = json.loads((bundle_dir / "scenario.gt.json").read_text())
    predicates = [
        a["predicate"] for a in gt["evaluation_criteria"]["env_assertions"]
    ]
    assert predicates == [
        "purchase_order_recorded",
        "seller_order_recorded",
        "approval_log_recorded",
        "transaction_artifacts_consistent",
        "price_within_owned_constraints",
    ]


def test_new_expansion_task_carries_required_terms_predicate(tmp_path: Path) -> None:
    variants = task_variants_for(
        "marble_bargaining",
        cell_id="CU-A-marble_bargaining",
    )
    kwargs = variants[4].loader_kwargs
    bundle = load_bargaining_scenario(**kwargs)
    bundle_dir = materialize_bargaining_bundle(bundle, tmp_path / "scenario")
    gt = json.loads((bundle_dir / "scenario.gt.json").read_text())
    assertions = gt["evaluation_criteria"]["env_assertions"]
    required_terms = [
        assertion
        for assertion in assertions
        if assertion["predicate"] == "required_terms_consistent"
    ]
    assert required_terms == [
        {
            "predicate": "required_terms_consistent",
            "args": {
                "transaction_id": "TXN-OE-104",
                "required_keys": [
                    "vendor_id",
                    "onboarding_status",
                    "tax_doc_id",
                ],
            },
        }
    ]

    context = json.loads((bundle_dir / "family_pack_context.json").read_text())
    assert context["required_terms"] == [
        "vendor_id",
        "onboarding_status",
        "tax_doc_id",
    ]


def test_expansion_materializer_writes_task_specific_tables(
    tmp_path: Path,
) -> None:
    variants = task_variants_for("marble_bargaining")
    by_transaction = {
        variant.loader_kwargs["transaction_id"]: variant.loader_kwargs
        for variant in variants
    }
    expected_tables = {
        "TXN-OE-101": {
            "harborview_procurement": {"budget_ledger", "purchase_orders"},
            "northstar_sales": {
                "inventory",
                "inventory_allocations",
                "price_book",
                "seller_orders",
            },
            "harborview_finance": {"approval_rules", "approval_log", "delegations"},
        },
        "TXN-OE-102": {
            "evergreen_procurement": {
                "budget_ledger",
                "receiving_windows",
                "purchase_orders",
            },
            "atlas_supply_sales": {
                "inventory",
                "price_book",
                "shipping_calendar",
                "cold_chain_surcharges",
                "seller_orders",
            },
            "evergreen_compliance": {
                "approval_rules",
                "approval_log",
                "shipment_risk_register",
                "delegations",
            },
        },
        "TXN-OE-103": {
            "meridian_it_procurement": {
                "contract_entitlements",
                "budget_ledger",
                "purchase_orders",
            },
            "omniworks_account_sales": {
                "customer_contracts",
                "seat_inventory",
                "price_book",
                "renewal_discounts",
                "seller_orders",
            },
            "meridian_vendor_management": {
                "approval_rules",
                "approval_log",
                "vendor_reviews",
                "delegations",
            },
        },
    }
    expected_transactions = set(expected_tables)
    assert expected_transactions <= set(by_transaction)

    for transaction_id, owners in expected_tables.items():
        bundle = load_bargaining_scenario(**by_transaction[transaction_id])
        bundle_dir = materialize_bargaining_bundle(
            bundle,
            tmp_path / transaction_id,
        )
        for owner_id, required_tables in owners.items():
            db_path = (
                bundle_dir
                / "resources"
                / "agents"
                / owner_id
                / "db"
                / "personal.sqlite"
            )
            assert db_path.is_file()
            with sqlite3.connect(db_path) as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                for table_name in (
                    "purchase_orders",
                    "seller_orders",
                    "approval_log",
                ):
                    if table_name in tables:
                        columns = {
                            row[1]
                            for row in conn.execute(
                                f"PRAGMA table_info({table_name})"
                            )
                        }
                        assert "terms_json" in columns
            assert required_tables <= tables
