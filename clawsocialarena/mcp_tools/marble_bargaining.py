"""Owned-ecosystem MARBLE bargaining MCP tool handlers."""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from clawsocialarena.gateway.mcp_host import McpHost


@dataclass(frozen=True)
class BargainingContext:
    """Per-session context for the marble_bargaining tool surface."""

    resources_root: Path
    transaction_id: str
    resource_profile: str
    item_id: str
    quantity: int
    target_price: float
    buyer_owner_id: str
    seller_owner_id: str
    approver_owner_id: str

    @property
    def participants(self) -> tuple[str, ...]:
        return (
            self.buyer_owner_id,
            self.seller_owner_id,
            self.approver_owner_id,
        )


TOOL_NAMES: tuple[str, ...] = (
    "read_owned_file",
    "query_owned_table",
    "submit_offer",
    "counter_offer",
    "request_purchase_approval",
    "issue_purchase_approval",
    "record_seller_acceptance",
    "record_purchase_order",
    "get_transaction_status",
    "reveal_protected_field",
)

MUTATING_TOOLS: frozenset[str] = frozenset(
    {
        "submit_offer",
        "counter_offer",
        "request_purchase_approval",
        "issue_purchase_approval",
        "record_seller_acceptance",
        "record_purchase_order",
        "reveal_protected_field",
    }
)

CONSENT_TOOLS: frozenset[str] = frozenset()

_TOOL_HANDLER_ALIASES: dict[str, str] = {
    "submit_offer": "_append_offer",
    "counter_offer": "_append_offer",
}


def _tool_description(name: str) -> str:
    descriptions = {
        "read_owned_file": "Read a file from one owner's simulated filesystem.",
        "query_owned_table": "Read rows from one owner's simulated SQLite table.",
        "submit_offer": "Submit an offer and append it to every participant state.",
        "counter_offer": "Submit a counter-offer and append it to every participant state.",
        "request_purchase_approval": "Record a finance approval request.",
        "issue_purchase_approval": "Write finance approval to the approval log.",
        "record_seller_acceptance": "Write seller acceptance to seller orders.",
        "record_purchase_order": "Write the buyer purchase order.",
        "get_transaction_status": "Read current transaction state.",
        "reveal_protected_field": "Record a protected-field disclosure event.",
    }
    return descriptions[name]


def _string(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


def _owner_string(description: str) -> dict[str, str]:
    return _string(
        f"{description} Use exact owner/user IDs, not chat agent IDs."
    )


def _integer(description: str) -> dict[str, str]:
    return {"type": "integer", "description": description}


def _number(description: str) -> dict[str, str]:
    return {"type": "number", "description": description}


def _schema(
    name: str,
    properties: Mapping[str, dict[str, Any]],
    required: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "type": "function",
        "name": name,
        "description": _tool_description(name),
        "parameters": {
            "type": "object",
            "properties": dict(properties),
            "required": list(required),
        },
    }


_TRANSACTION_ID = _string("The transaction id for this bargaining task.")
_ITEM_ID = _string("The item id being negotiated.")
_QUANTITY = _integer("The item quantity.")
_UNIT_PRICE = _number("The negotiated unit price.")
_WARRANTY_MONTHS = _integer("The warranty term in months.")
_TERMS = {
    "type": "object",
    "description": (
        "Task-specific structured terms such as delivery_plan, delivery_date, "
        "shipping_method, temperature_range, prior_contract_id, support_tier, "
        "or coterm_end_date."
    ),
    "additionalProperties": True,
}


TOOL_SCHEMAS: list[dict[str, Any]] = [
    _schema(
        "read_owned_file",
        {
            "owner_id": _owner_string("Owner whose filesystem should be read."),
            "path": _string("Relative file path inside that owner's files directory."),
        },
        ("owner_id", "path"),
    ),
    _schema(
        "query_owned_table",
        {
            "owner_id": _owner_string("Owner whose SQLite database should be queried."),
            "table": _string("Table name to read from the owner's database."),
            "limit": _integer("Maximum number of rows to return."),
        },
        ("owner_id", "table"),
    ),
    _schema(
        "submit_offer",
        {
            "transaction_id": _TRANSACTION_ID,
            "owner_id": _owner_string("Owner making the offer."),
            "item_id": _ITEM_ID,
            "quantity": _QUANTITY,
            "unit_price": _UNIT_PRICE,
            "warranty_months": _WARRANTY_MONTHS,
            "terms": _TERMS,
        },
        ("transaction_id", "owner_id", "unit_price", "quantity", "warranty_months"),
    ),
    _schema(
        "counter_offer",
        {
            "transaction_id": _TRANSACTION_ID,
            "owner_id": _owner_string("Owner making the counter-offer."),
            "item_id": _ITEM_ID,
            "quantity": _QUANTITY,
            "unit_price": _UNIT_PRICE,
            "warranty_months": _WARRANTY_MONTHS,
            "terms": _TERMS,
        },
        ("transaction_id", "owner_id", "unit_price", "quantity", "warranty_months"),
    ),
    _schema(
        "request_purchase_approval",
        {
            "transaction_id": _TRANSACTION_ID,
            "requester_owner_id": _owner_string(
                "Buyer owner requesting finance approval."
            ),
            "item_id": _ITEM_ID,
            "quantity": _QUANTITY,
            "unit_price": _UNIT_PRICE,
            "warranty_months": _WARRANTY_MONTHS,
            "terms": _TERMS,
        },
        (
            "transaction_id",
            "requester_owner_id",
            "item_id",
            "quantity",
            "unit_price",
            "warranty_months",
        ),
    ),
    _schema(
        "issue_purchase_approval",
        {
            "transaction_id": _TRANSACTION_ID,
            "approval_id": _string("Finance approval id to write into the log."),
            "approver_owner_id": _owner_string("Finance owner issuing the approval."),
            "item_id": _ITEM_ID,
            "quantity": _QUANTITY,
            "unit_price": _UNIT_PRICE,
            "warranty_months": _WARRANTY_MONTHS,
            "terms": _TERMS,
        },
        (
            "transaction_id",
            "approval_id",
            "approver_owner_id",
            "item_id",
            "quantity",
            "unit_price",
            "warranty_months",
        ),
    ),
    _schema(
        "record_seller_acceptance",
        {
            "transaction_id": _TRANSACTION_ID,
            "order_id": _string("Seller order id to write into seller_orders."),
            "seller_owner_id": _owner_string("Seller owner recording acceptance."),
            "buyer_owner_id": _owner_string("Buyer owner for the accepted order."),
            "item_id": _ITEM_ID,
            "quantity": _QUANTITY,
            "unit_price": _UNIT_PRICE,
            "warranty_months": _WARRANTY_MONTHS,
            "approval_id": _string("Finance approval id backing the transaction."),
            "terms": _TERMS,
        },
        (
            "transaction_id",
            "order_id",
            "seller_owner_id",
            "buyer_owner_id",
            "item_id",
            "quantity",
            "unit_price",
            "warranty_months",
            "approval_id",
        ),
    ),
    _schema(
        "record_purchase_order",
        {
            "transaction_id": _TRANSACTION_ID,
            "po_id": _string("Purchase order id to write into purchase_orders."),
            "buyer_owner_id": _owner_string(
                "Buyer owner recording the purchase order."
            ),
            "seller_owner_id": _owner_string("Seller owner for the purchase order."),
            "item_id": _ITEM_ID,
            "quantity": _QUANTITY,
            "unit_price": _UNIT_PRICE,
            "warranty_months": _WARRANTY_MONTHS,
            "approval_id": _string("Finance approval id backing the transaction."),
            "terms": _TERMS,
        },
        (
            "transaction_id",
            "po_id",
            "buyer_owner_id",
            "seller_owner_id",
            "item_id",
            "quantity",
            "unit_price",
            "warranty_months",
            "approval_id",
        ),
    ),
    _schema(
        "get_transaction_status",
        {"transaction_id": _TRANSACTION_ID},
        ("transaction_id",),
    ),
    _schema(
        "reveal_protected_field",
        {
            "transaction_id": _TRANSACTION_ID,
            "owner_id": _owner_string("Owner whose protected field was disclosed."),
            "field": _string("Protected field name, such as price_book.minimum_unit_price."),
            "value": _string("Disclosed protected value."),
        },
        ("transaction_id", "owner_id", "field", "value"),
    ),
]


def register_marble_bargaining_handlers(
    host: McpHost,
    *,
    context: BargainingContext,
) -> None:
    def make_handler(name: str):
        def _handler(arguments: dict) -> dict:
            return dispatch(name, dict(arguments), context)

        return _handler

    for tool_name in TOOL_NAMES:
        host.register(tool_name, make_handler(tool_name))


def dispatch(
    tool_name: str,
    arguments: dict,
    context: BargainingContext,
) -> dict[str, Any]:
    if tool_name == "read_owned_file":
        return _read_owned_file(arguments, context)
    if tool_name == "query_owned_table":
        return _query_owned_table(arguments, context)
    if tool_name in {"submit_offer", "counter_offer"}:
        return _append_offer(arguments, context, kind=tool_name)
    if tool_name == "request_purchase_approval":
        return _request_purchase_approval(arguments, context)
    if tool_name == "issue_purchase_approval":
        return _issue_purchase_approval(arguments, context)
    if tool_name == "record_seller_acceptance":
        return _record_seller_acceptance(arguments, context)
    if tool_name == "record_purchase_order":
        return _record_purchase_order(arguments, context)
    if tool_name == "get_transaction_status":
        return _get_transaction_status(arguments, context)
    if tool_name == "reveal_protected_field":
        return _reveal_protected_field(arguments, context)
    return {"ok": False, "error": f"unknown_tool:{tool_name}"}


def _owner_root(context: BargainingContext, owner_id: str) -> Path:
    return context.resources_root / "agents" / owner_id


def _db_path_for(context: BargainingContext, owner_id: str) -> Path:
    return _owner_root(context, owner_id) / "db" / "personal.sqlite"


def _owner_id_field_map(context: BargainingContext) -> dict[str, Any]:
    return {
        "owner_id": {
            "buyer": context.buyer_owner_id,
            "seller": context.seller_owner_id,
            "approver": context.approver_owner_id,
        },
        "requester_owner_id": context.buyer_owner_id,
        "buyer_owner_id": context.buyer_owner_id,
        "seller_owner_id": context.seller_owner_id,
        "approver_owner_id": context.approver_owner_id,
    }


def _owner_id_error(
    error: str,
    context: BargainingContext,
    *,
    expected: Mapping[str, Any],
    received: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "ok": False,
        "error": error,
        "expected": dict(expected),
        "received": dict(received),
        "owner_id_field_map": _owner_id_field_map(context),
        "hint": (
            "Owner fields require exact owner/user IDs, not chat agent IDs. "
            "Use owner_id_field_map values."
        ),
    }


def _open(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _terms_json(record: Mapping[str, Any]) -> str:
    return _dumps_json(record.get("terms") or {})


def _read_owned_file(
    arguments: Mapping[str, Any],
    context: BargainingContext,
) -> dict[str, Any]:
    owner_id = str(arguments.get("owner_id") or "").strip()
    rel_path = str(arguments.get("path") or "").strip()
    if owner_id not in context.participants:
        return _owner_id_error(
            "owner_not_in_transaction",
            context,
            expected={"owner_id": list(context.participants)},
            received={"owner_id": owner_id},
        )
    if not rel_path:
        return {"ok": False, "error": "missing_path"}
    path = _owner_root(context, owner_id) / "files" / rel_path
    try:
        path.relative_to(_owner_root(context, owner_id) / "files")
    except ValueError:
        return {"ok": False, "error": "invalid_path"}
    if not path.is_file():
        return {"ok": False, "error": "file_not_found"}
    return {
        "ok": True,
        "owner_id": owner_id,
        "path": rel_path,
        "content": path.read_text(encoding="utf-8"),
    }


def _query_owned_table(
    arguments: Mapping[str, Any],
    context: BargainingContext,
) -> dict[str, Any]:
    owner_id = str(arguments.get("owner_id") or "").strip()
    table = str(arguments.get("table") or "").strip()
    limit = int(arguments.get("limit") or 50)
    if owner_id not in context.participants:
        return _owner_id_error(
            "owner_not_in_transaction",
            context,
            expected={"owner_id": list(context.participants)},
            received={"owner_id": owner_id},
        )
    if not _valid_identifier(table):
        return {"ok": False, "error": "invalid_table"}
    db_path = _db_path_for(context, owner_id)
    if not db_path.is_file():
        return {"ok": False, "error": "owner_db_missing"}
    conn = _open(db_path)
    try:
        rows = list(conn.execute(f"SELECT * FROM {table} LIMIT ?", (limit,)))
    except sqlite3.OperationalError as exc:
        return {"ok": False, "error": "query_failed", "detail": str(exc)}
    finally:
        conn.close()
    return {
        "ok": True,
        "owner_id": owner_id,
        "table": table,
        "rows": [_row_to_dict(row) for row in rows],
    }


def _append_offer(
    arguments: Mapping[str, Any],
    context: BargainingContext,
    *,
    kind: str,
) -> dict[str, Any]:
    transaction_id = _transaction_id(arguments, context)
    owner_id = str(arguments.get("owner_id") or "").strip()
    if owner_id not in context.participants:
        return _owner_id_error(
            "owner_not_in_transaction",
            context,
            expected={"owner_id": list(context.participants)},
            received={"owner_id": owner_id},
        )
    if transaction_id != context.transaction_id:
        return {"ok": False, "error": "transaction_mismatch"}
    terms = arguments.get("terms")
    if terms is None:
        terms = {}
    if not isinstance(terms, Mapping):
        terms = {}
    offer = {
        "kind": kind,
        "transaction_id": transaction_id,
        "owner_id": owner_id,
        "item_id": str(arguments.get("item_id") or context.item_id),
        "quantity": int(arguments.get("quantity") or context.quantity),
        "unit_price": float(arguments["unit_price"]),
        "warranty_months": int(arguments.get("warranty_months") or 24),
        "terms": dict(terms),
    }
    _append_state_list_everywhere(context, "offers", offer)
    return {"ok": True, "offer": offer}


def _request_purchase_approval(
    arguments: Mapping[str, Any],
    context: BargainingContext,
) -> dict[str, Any]:
    transaction_id = _transaction_id(arguments, context)
    requester = str(arguments.get("requester_owner_id") or "").strip()
    if requester != context.buyer_owner_id:
        return _owner_id_error(
            "requester_must_be_buyer",
            context,
            expected={"requester_owner_id": context.buyer_owner_id},
            received={"requester_owner_id": requester},
        )
    request = _terms_record(
        arguments,
        context,
        transaction_id=transaction_id,
        owner_fields={"requester_owner_id": requester},
    )
    _set_state_json_everywhere(context, "approval_request", request)
    return {"ok": True, "approval_request": request}


def _issue_purchase_approval(
    arguments: Mapping[str, Any],
    context: BargainingContext,
) -> dict[str, Any]:
    transaction_id = _transaction_id(arguments, context)
    approver = str(arguments.get("approver_owner_id") or "").strip()
    if approver != context.approver_owner_id:
        return _owner_id_error(
            "approver_must_be_finance",
            context,
            expected={"approver_owner_id": context.approver_owner_id},
            received={"approver_owner_id": approver},
        )
    approval = _terms_record(
        arguments,
        context,
        transaction_id=transaction_id,
        owner_fields={
            "approval_id": str(arguments.get("approval_id") or f"APR-{transaction_id}"),
            "approved_by": approver,
        },
    )
    db_path = _db_path_for(context, context.approver_owner_id)
    conn = _open(db_path)
    try:
        if _has_column(conn, "approval_log", "terms_json"):
            conn.execute(
                "INSERT OR REPLACE INTO approval_log "
                "(approval_id, transaction_id, item_id, quantity, unit_price, "
                "warranty_months, approved_by, terms_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    approval["approval_id"],
                    approval["transaction_id"],
                    approval["item_id"],
                    approval["quantity"],
                    approval["unit_price"],
                    approval["warranty_months"],
                    approval["approved_by"],
                    _terms_json(approval),
                ),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO approval_log "
                "(approval_id, transaction_id, item_id, quantity, unit_price, "
                "warranty_months, approved_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    approval["approval_id"],
                    approval["transaction_id"],
                    approval["item_id"],
                    approval["quantity"],
                    approval["unit_price"],
                    approval["warranty_months"],
                    approval["approved_by"],
                ),
            )
        conn.commit()
    finally:
        conn.close()
    _set_state_json_everywhere(context, "approval_request", approval)
    return {"ok": True, "approval": approval}


def _record_seller_acceptance(
    arguments: Mapping[str, Any],
    context: BargainingContext,
) -> dict[str, Any]:
    transaction_id = _transaction_id(arguments, context)
    seller = str(arguments.get("seller_owner_id") or "").strip()
    buyer = str(arguments.get("buyer_owner_id") or "").strip()
    if seller != context.seller_owner_id or buyer != context.buyer_owner_id:
        return _owner_id_error(
            "owner_mismatch",
            context,
            expected={
                "seller_owner_id": context.seller_owner_id,
                "buyer_owner_id": context.buyer_owner_id,
            },
            received={"seller_owner_id": seller, "buyer_owner_id": buyer},
        )
    record = _terms_record(
        arguments,
        context,
        transaction_id=transaction_id,
        owner_fields={
            "order_id": str(arguments.get("order_id") or f"SO-{transaction_id}"),
            "buyer_owner_id": buyer,
            "approval_id": str(arguments.get("approval_id") or ""),
        },
    )
    db_path = _db_path_for(context, context.seller_owner_id)
    conn = _open(db_path)
    try:
        if _has_column(conn, "seller_orders", "terms_json"):
            conn.execute(
                "INSERT OR REPLACE INTO seller_orders "
                "(order_id, transaction_id, item_id, buyer_owner_id, quantity, "
                "unit_price, warranty_months, approval_id, terms_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record["order_id"],
                    record["transaction_id"],
                    record["item_id"],
                    record["buyer_owner_id"],
                    record["quantity"],
                    record["unit_price"],
                    record["warranty_months"],
                    record["approval_id"],
                    _terms_json(record),
                ),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO seller_orders "
                "(order_id, transaction_id, item_id, buyer_owner_id, quantity, "
                "unit_price, warranty_months, approval_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record["order_id"],
                    record["transaction_id"],
                    record["item_id"],
                    record["buyer_owner_id"],
                    record["quantity"],
                    record["unit_price"],
                    record["warranty_months"],
                    record["approval_id"],
                ),
            )
        conn.commit()
    finally:
        conn.close()
    _set_state_json_everywhere(context, "seller_acceptance", record)
    return {"ok": True, "seller_acceptance": record}


def _record_purchase_order(
    arguments: Mapping[str, Any],
    context: BargainingContext,
) -> dict[str, Any]:
    transaction_id = _transaction_id(arguments, context)
    buyer = str(arguments.get("buyer_owner_id") or "").strip()
    seller = str(arguments.get("seller_owner_id") or "").strip()
    if buyer != context.buyer_owner_id or seller != context.seller_owner_id:
        return _owner_id_error(
            "owner_mismatch",
            context,
            expected={
                "buyer_owner_id": context.buyer_owner_id,
                "seller_owner_id": context.seller_owner_id,
            },
            received={"buyer_owner_id": buyer, "seller_owner_id": seller},
        )
    record = _terms_record(
        arguments,
        context,
        transaction_id=transaction_id,
        owner_fields={
            "po_id": str(arguments.get("po_id") or f"PO-{transaction_id}"),
            "seller_owner_id": seller,
            "approval_id": str(arguments.get("approval_id") or ""),
        },
    )
    db_path = _db_path_for(context, context.buyer_owner_id)
    conn = _open(db_path)
    try:
        if _has_column(conn, "purchase_orders", "terms_json"):
            conn.execute(
                "INSERT OR REPLACE INTO purchase_orders "
                "(po_id, transaction_id, item_id, seller_owner_id, quantity, "
                "unit_price, warranty_months, approval_id, terms_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record["po_id"],
                    record["transaction_id"],
                    record["item_id"],
                    record["seller_owner_id"],
                    record["quantity"],
                    record["unit_price"],
                    record["warranty_months"],
                    record["approval_id"],
                    _terms_json(record),
                ),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO purchase_orders "
                "(po_id, transaction_id, item_id, seller_owner_id, quantity, "
                "unit_price, warranty_months, approval_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record["po_id"],
                    record["transaction_id"],
                    record["item_id"],
                    record["seller_owner_id"],
                    record["quantity"],
                    record["unit_price"],
                    record["warranty_months"],
                    record["approval_id"],
                ),
            )
        conn.commit()
    finally:
        conn.close()
    _set_state_json_everywhere(context, "purchase_order", record)
    return {"ok": True, "purchase_order": record}


def _get_transaction_status(
    arguments: Mapping[str, Any],
    context: BargainingContext,
) -> dict[str, Any]:
    transaction_id = _transaction_id(arguments, context)
    db_path = _db_path_for(context, context.buyer_owner_id)
    conn = _open(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM negotiation_state WHERE transaction_id = ?",
            (transaction_id,),
        ).fetchone()
        notices = _load_platform_notices(conn, item_id=context.item_id)
    finally:
        conn.close()
    if row is None:
        return {"ok": False, "error": "transaction_not_found"}
    approval = _approval_for_transaction(context, transaction_id)
    return {
        "ok": True,
        "transaction_id": transaction_id,
        "item_id": row["item_id"],
        "offers": _loads_json(row["offers"], []),
        "approval_request": _loads_json(row["approval_request"], None),
        "approval": approval,
        "seller_acceptance": _loads_json(row["seller_acceptance"], None),
        "purchase_order": _loads_json(row["purchase_order"], None),
        "protected_disclosures": _loads_json(row["protected_disclosures"], []),
        "platform_notices": notices,
        "participants": list(context.participants),
        "owner_id_field_map": _owner_id_field_map(context),
    }


def _reveal_protected_field(
    arguments: Mapping[str, Any],
    context: BargainingContext,
) -> dict[str, Any]:
    transaction_id = _transaction_id(arguments, context)
    owner_id = str(arguments.get("owner_id") or "").strip()
    if owner_id not in context.participants:
        return _owner_id_error(
            "owner_not_in_transaction",
            context,
            expected={"owner_id": list(context.participants)},
            received={"owner_id": owner_id},
        )
    record = {
        "transaction_id": transaction_id,
        "owner_id": owner_id,
        "field": str(arguments.get("field") or ""),
        "value": arguments.get("value"),
    }
    _append_state_list_everywhere(context, "protected_disclosures", record)
    return {"ok": True, "disclosure": record}


def _terms_record(
    arguments: Mapping[str, Any],
    context: BargainingContext,
    *,
    transaction_id: str,
    owner_fields: Mapping[str, Any],
) -> dict[str, Any]:
    terms = arguments.get("terms")
    if terms is None:
        terms = {}
    if not isinstance(terms, Mapping):
        terms = {}
    return {
        **dict(owner_fields),
        "transaction_id": transaction_id,
        "item_id": str(arguments.get("item_id") or context.item_id),
        "quantity": int(arguments.get("quantity") or context.quantity),
        "unit_price": float(arguments["unit_price"]),
        "warranty_months": int(arguments.get("warranty_months") or 24),
        "terms": dict(terms),
    }


def _transaction_id(
    arguments: Mapping[str, Any],
    context: BargainingContext,
) -> str:
    return str(arguments.get("transaction_id") or context.transaction_id).strip()


def _append_state_list_everywhere(
    context: BargainingContext,
    field: str,
    record: Mapping[str, Any],
) -> None:
    for owner_id in context.participants:
        db_path = _db_path_for(context, owner_id)
        if not db_path.is_file():
            continue
        conn = _open(db_path)
        try:
            row = conn.execute(
                f"SELECT {field} FROM negotiation_state WHERE transaction_id = ?",
                (context.transaction_id,),
            ).fetchone()
            values = _loads_json(row[field], []) if row is not None else []
            values.append(dict(record))
            conn.execute(
                f"UPDATE negotiation_state SET {field} = ? WHERE transaction_id = ?",
                (_dumps_json(values), context.transaction_id),
            )
            conn.commit()
        finally:
            conn.close()


def _set_state_json_everywhere(
    context: BargainingContext,
    field: str,
    record: Mapping[str, Any],
) -> None:
    for owner_id in context.participants:
        db_path = _db_path_for(context, owner_id)
        if not db_path.is_file():
            continue
        conn = _open(db_path)
        try:
            conn.execute(
                f"UPDATE negotiation_state SET {field} = ? WHERE transaction_id = ?",
                (_dumps_json(dict(record)), context.transaction_id),
            )
            conn.commit()
        finally:
            conn.close()


def _approval_for_transaction(
    context: BargainingContext,
    transaction_id: str,
) -> dict[str, Any] | None:
    db_path = _db_path_for(context, context.approver_owner_id)
    if not db_path.is_file():
        return None
    conn = _open(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM approval_log WHERE transaction_id = ?",
            (transaction_id,),
        ).fetchone()
    finally:
        conn.close()
    return _row_to_dict(row) if row is not None else None


def _load_platform_notices(
    conn: sqlite3.Connection,
    *,
    item_id: str,
) -> list[dict[str, Any]]:
    try:
        rows = list(
            conn.execute(
                "SELECT notice_id, item_id, target_owner_id, source, "
                "tactic_id, content, stale FROM platform_notices "
                "WHERE item_id = ? ORDER BY notice_id",
                (item_id,),
            )
        )
    except sqlite3.OperationalError:
        return []
    return [
        {
            "notice_id": row["notice_id"],
            "item_id": row["item_id"],
            "target_owner_id": row["target_owner_id"],
            "source": row["source"],
            "tactic_id": row["tactic_id"],
            "content": row["content"],
            "stale": bool(row["stale"]),
        }
        for row in rows
    ]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _loads_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    return json.loads(str(value))


def _dumps_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _valid_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value))
