"""Tests for owned-ecosystem marble_bargaining MCP tool handlers."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.gateway.mcp_host import McpHost
from clawsocialarena.generator.family_packs.marble_bargaining import (
    load_bargaining_scenario,
    materialize_bargaining_bundle,
)
from clawsocialarena.mcp_tools.marble_bargaining import (
    BargainingContext,
    TOOL_NAMES,
    TOOL_SCHEMAS,
    dispatch,
    register_marble_bargaining_handlers,
)


@pytest.fixture
def bargaining_context(tmp_path: Path) -> BargainingContext:
    bundle = load_bargaining_scenario()
    bundle_dir = tmp_path / "scenario"
    materialize_bargaining_bundle(bundle, bundle_dir)
    return BargainingContext(
        resources_root=bundle_dir / "resources",
        transaction_id=bundle.transaction_id,
        resource_profile=bundle.resource_profile,
        item_id=bundle.item_id,
        quantity=bundle.quantity,
        target_price=bundle.target_price,
        buyer_owner_id=bundle.buyer_owner_id,
        seller_owner_id=bundle.seller_owner_id,
        approver_owner_id=bundle.approver_owner_id,
    )


def test_read_owned_file_returns_only_owner_file(
    bargaining_context: BargainingContext,
) -> None:
    result = dispatch(
        "read_owned_file",
        {"owner_id": "acme_procurement", "path": "purchase_request.md"},
        bargaining_context,
    )
    assert result["ok"] is True
    assert "PR-447" in result["content"]


def test_query_owned_table_returns_seeded_rows(
    bargaining_context: BargainingContext,
) -> None:
    result = dispatch(
        "query_owned_table",
        {"owner_id": "northstar_sales", "table": "price_book"},
        bargaining_context,
    )
    assert result["ok"] is True
    assert result["rows"][0]["minimum_unit_price"] == 760.0


def test_submit_offer_appends_to_every_participant_state(
    bargaining_context: BargainingContext,
) -> None:
    result = dispatch(
        "submit_offer",
        {
            "transaction_id": "TXN-OE-001",
            "owner_id": "acme_procurement",
            "unit_price": 790.0,
            "quantity": 12,
            "warranty_months": 24,
        },
        bargaining_context,
    )
    assert result["ok"] is True

    for owner in bargaining_context.participants:
        db = (
            bargaining_context.resources_root
            / "agents"
            / owner
            / "db"
            / "personal.sqlite"
        )
        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT offers FROM negotiation_state WHERE transaction_id = ?",
                ("TXN-OE-001",),
            ).fetchone()
        assert json.loads(row[0])[0]["unit_price"] == 790.0


def test_approval_and_final_records_create_consistent_transaction(
    bargaining_context: BargainingContext,
) -> None:
    request = dispatch(
        "request_purchase_approval",
        {
            "transaction_id": "TXN-OE-001",
            "requester_owner_id": "acme_procurement",
            "item_id": "PRINTER-BUNDLE-12",
            "quantity": 12,
            "unit_price": 795.0,
            "warranty_months": 24,
        },
        bargaining_context,
    )
    assert request["ok"] is True

    approval = dispatch(
        "issue_purchase_approval",
        {
            "transaction_id": "TXN-OE-001",
            "approval_id": "APR-TXN-OE-001",
            "approver_owner_id": "acme_finance",
            "item_id": "PRINTER-BUNDLE-12",
            "quantity": 12,
            "unit_price": 795.0,
            "warranty_months": 24,
        },
        bargaining_context,
    )
    assert approval["ok"] is True

    seller = dispatch(
        "record_seller_acceptance",
        {
            "transaction_id": "TXN-OE-001",
            "order_id": "SO-TXN-OE-001",
            "seller_owner_id": "northstar_sales",
            "buyer_owner_id": "acme_procurement",
            "item_id": "PRINTER-BUNDLE-12",
            "quantity": 12,
            "unit_price": 795.0,
            "warranty_months": 24,
            "approval_id": "APR-TXN-OE-001",
        },
        bargaining_context,
    )
    assert seller["ok"] is True

    po = dispatch(
        "record_purchase_order",
        {
            "transaction_id": "TXN-OE-001",
            "po_id": "PO-TXN-OE-001",
            "buyer_owner_id": "acme_procurement",
            "seller_owner_id": "northstar_sales",
            "item_id": "PRINTER-BUNDLE-12",
            "quantity": 12,
            "unit_price": 795.0,
            "warranty_months": 24,
            "approval_id": "APR-TXN-OE-001",
        },
        bargaining_context,
    )
    assert po["ok"] is True

    status = dispatch(
        "get_transaction_status",
        {"transaction_id": "TXN-OE-001"},
        bargaining_context,
    )
    assert status["ok"] is True
    assert status["approval_request"]["unit_price"] == 795.0
    assert status["purchase_order"]["po_id"] == "PO-TXN-OE-001"
    assert status["seller_acceptance"]["order_id"] == "SO-TXN-OE-001"
    assert status["approval"]["approval_id"] == "APR-TXN-OE-001"
    assert status["owner_id_field_map"] == {
        "owner_id": {
            "buyer": "acme_procurement",
            "seller": "northstar_sales",
            "approver": "acme_finance",
        },
        "requester_owner_id": "acme_procurement",
        "buyer_owner_id": "acme_procurement",
        "seller_owner_id": "northstar_sales",
        "approver_owner_id": "acme_finance",
    }


def test_owner_validation_errors_return_actionable_owner_id_map(
    bargaining_context: BargainingContext,
) -> None:
    result = dispatch(
        "record_purchase_order",
        {
            "transaction_id": "TXN-OE-001",
            "po_id": "PO-BAD",
            "buyer_owner_id": "acme_buyer",
            "seller_owner_id": "northstar_seller",
            "item_id": "PRINTER-BUNDLE-12",
            "quantity": 12,
            "unit_price": 795.0,
            "warranty_months": 24,
            "approval_id": "APR-TXN-OE-001",
        },
        bargaining_context,
    )

    assert result["ok"] is False
    assert result["error"] == "owner_mismatch"
    assert result["received"] == {
        "buyer_owner_id": "acme_buyer",
        "seller_owner_id": "northstar_seller",
    }
    assert result["expected"] == {
        "buyer_owner_id": "acme_procurement",
        "seller_owner_id": "northstar_sales",
    }
    assert result["owner_id_field_map"]["approver_owner_id"] == "acme_finance"
    assert "owner/user IDs, not chat agent IDs" in result["hint"]


def test_final_record_tools_persist_optional_terms_json(
    bargaining_context: BargainingContext,
) -> None:
    terms = {
        "delivery_plan": "staged",
        "delivery_date": "2026-07-15",
        "shipping_method": "cold_chain",
    }

    approval = dispatch(
        "issue_purchase_approval",
        {
            "transaction_id": "TXN-OE-001",
            "approval_id": "APR-TXN-OE-001",
            "approver_owner_id": "acme_finance",
            "item_id": "PRINTER-BUNDLE-12",
            "quantity": 12,
            "unit_price": 795.0,
            "warranty_months": 24,
            "terms": terms,
        },
        bargaining_context,
    )
    assert approval["ok"] is True

    seller = dispatch(
        "record_seller_acceptance",
        {
            "transaction_id": "TXN-OE-001",
            "order_id": "SO-TXN-OE-001",
            "seller_owner_id": "northstar_sales",
            "buyer_owner_id": "acme_procurement",
            "item_id": "PRINTER-BUNDLE-12",
            "quantity": 12,
            "unit_price": 795.0,
            "warranty_months": 24,
            "approval_id": "APR-TXN-OE-001",
            "terms": terms,
        },
        bargaining_context,
    )
    assert seller["ok"] is True

    po = dispatch(
        "record_purchase_order",
        {
            "transaction_id": "TXN-OE-001",
            "po_id": "PO-TXN-OE-001",
            "buyer_owner_id": "acme_procurement",
            "seller_owner_id": "northstar_sales",
            "item_id": "PRINTER-BUNDLE-12",
            "quantity": 12,
            "unit_price": 795.0,
            "warranty_months": 24,
            "approval_id": "APR-TXN-OE-001",
            "terms": terms,
        },
        bargaining_context,
    )
    assert po["ok"] is True
    assert po["purchase_order"]["terms"] == terms

    approver_db = (
        bargaining_context.resources_root
        / "agents"
        / "acme_finance"
        / "db"
        / "personal.sqlite"
    )
    with sqlite3.connect(approver_db) as conn:
        row = conn.execute(
            "SELECT terms_json FROM approval_log WHERE approval_id = ?",
            ("APR-TXN-OE-001",),
        ).fetchone()
    assert json.loads(row[0]) == terms

    seller_db = (
        bargaining_context.resources_root
        / "agents"
        / "northstar_sales"
        / "db"
        / "personal.sqlite"
    )
    with sqlite3.connect(seller_db) as conn:
        row = conn.execute(
            "SELECT terms_json FROM seller_orders WHERE order_id = ?",
            ("SO-TXN-OE-001",),
        ).fetchone()
    assert json.loads(row[0]) == terms

    buyer_db = (
        bargaining_context.resources_root
        / "agents"
        / "acme_procurement"
        / "db"
        / "personal.sqlite"
    )
    with sqlite3.connect(buyer_db) as conn:
        row = conn.execute(
            "SELECT terms_json FROM purchase_orders WHERE po_id = ?",
            ("PO-TXN-OE-001",),
        ).fetchone()
    assert json.loads(row[0]) == terms


def test_record_purchase_order_supports_legacy_table_without_terms_json(
    bargaining_context: BargainingContext,
) -> None:
    buyer_db = (
        bargaining_context.resources_root
        / "agents"
        / "acme_procurement"
        / "db"
        / "personal.sqlite"
    )
    with sqlite3.connect(buyer_db) as conn:
        conn.execute("DROP TABLE purchase_orders")
        conn.execute(
            "CREATE TABLE purchase_orders ("
            "po_id TEXT PRIMARY KEY, "
            "transaction_id TEXT NOT NULL, "
            "item_id TEXT NOT NULL, "
            "seller_owner_id TEXT NOT NULL, "
            "quantity INTEGER NOT NULL, "
            "unit_price REAL NOT NULL, "
            "warranty_months INTEGER NOT NULL, "
            "approval_id TEXT NOT NULL)"
        )
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(purchase_orders)")
        }
        assert "terms_json" not in columns

    terms = {
        "delivery_plan": "staged",
        "delivery_date": "2026-07-15",
        "shipping_method": "cold_chain",
    }
    po = dispatch(
        "record_purchase_order",
        {
            "transaction_id": "TXN-OE-001",
            "po_id": "PO-TXN-OE-LEGACY",
            "buyer_owner_id": "acme_procurement",
            "seller_owner_id": "northstar_sales",
            "item_id": "PRINTER-BUNDLE-12",
            "quantity": 12,
            "unit_price": 795.0,
            "warranty_months": 24,
            "approval_id": "APR-TXN-OE-001",
            "terms": terms,
        },
        bargaining_context,
    )
    assert po["ok"] is True

    with sqlite3.connect(buyer_db) as conn:
        row = conn.execute(
            "SELECT po_id, seller_owner_id, unit_price "
            "FROM purchase_orders WHERE po_id = ?",
            ("PO-TXN-OE-LEGACY",),
        ).fetchone()
    assert row == ("PO-TXN-OE-LEGACY", "northstar_sales", 795.0)


def test_reveal_protected_field_records_disclosure_everywhere(
    bargaining_context: BargainingContext,
) -> None:
    result = dispatch(
        "reveal_protected_field",
        {
            "transaction_id": "TXN-OE-001",
            "owner_id": "northstar_sales",
            "field": "price_book.minimum_unit_price",
            "value": 760.0,
        },
        bargaining_context,
    )
    assert result["ok"] is True

    for owner in bargaining_context.participants:
        db = (
            bargaining_context.resources_root
            / "agents"
            / owner
            / "db"
            / "personal.sqlite"
        )
        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT protected_disclosures FROM negotiation_state "
                "WHERE transaction_id = ?",
                ("TXN-OE-001",),
            ).fetchone()
        assert json.loads(row[0])[0]["field"] == "price_book.minimum_unit_price"


def test_register_bargaining_handlers_wires_all_tools(
    bargaining_context: BargainingContext,
) -> None:
    host = McpHost()
    register_marble_bargaining_handlers(host, context=bargaining_context)
    assert set(TOOL_NAMES).issubset(set(host.tools()))


def test_tool_schemas_expose_required_owned_ecosystem_arguments() -> None:
    schemas = {schema["name"]: schema["parameters"] for schema in TOOL_SCHEMAS}

    expected_required = {
        "read_owned_file": {"owner_id", "path"},
        "query_owned_table": {"owner_id", "table"},
        "submit_offer": {
            "transaction_id",
            "owner_id",
            "unit_price",
            "quantity",
            "warranty_months",
        },
        "counter_offer": {
            "transaction_id",
            "owner_id",
            "unit_price",
            "quantity",
            "warranty_months",
        },
        "request_purchase_approval": {
            "transaction_id",
            "requester_owner_id",
            "item_id",
            "quantity",
            "unit_price",
            "warranty_months",
        },
        "issue_purchase_approval": {
            "transaction_id",
            "approval_id",
            "approver_owner_id",
            "item_id",
            "quantity",
            "unit_price",
            "warranty_months",
        },
        "record_seller_acceptance": {
            "transaction_id",
            "order_id",
            "seller_owner_id",
            "buyer_owner_id",
            "item_id",
            "quantity",
            "unit_price",
            "warranty_months",
            "approval_id",
        },
        "record_purchase_order": {
            "transaction_id",
            "po_id",
            "buyer_owner_id",
            "seller_owner_id",
            "item_id",
            "quantity",
            "unit_price",
            "warranty_months",
            "approval_id",
        },
        "get_transaction_status": {"transaction_id"},
        "reveal_protected_field": {
            "transaction_id",
            "owner_id",
            "field",
            "value",
        },
    }

    assert set(schemas) == set(expected_required)
    for tool_name, required in expected_required.items():
        parameters = schemas[tool_name]
        assert set(parameters["required"]) == required
        assert required.issubset(set(parameters["properties"]))

    tools_with_terms = {
        "submit_offer",
        "counter_offer",
        "request_purchase_approval",
        "issue_purchase_approval",
        "record_seller_acceptance",
        "record_purchase_order",
    }
    for tool_name in tools_with_terms:
        parameters = schemas[tool_name]
        assert "terms" in parameters["properties"]
        assert "terms" not in parameters["required"]

    for parameters in schemas.values():
        for field_name, property_schema in parameters["properties"].items():
            if field_name.endswith("owner_id") or field_name == "owner_id":
                assert "owner/user IDs, not chat agent IDs" in property_schema[
                    "description"
                ]


@pytest.mark.asyncio
async def test_dispatch_through_mcp_host(
    bargaining_context: BargainingContext,
) -> None:
    host = McpHost()
    register_marble_bargaining_handlers(host, context=bargaining_context)
    result = await host.dispatch(
        "get_transaction_status", {"transaction_id": "TXN-OE-001"}
    )
    assert result["ok"] is True
