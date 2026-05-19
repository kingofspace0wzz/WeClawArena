"""MARBLE bidding MCP tool handlers."""
from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from clawsocialarena.gateway.mcp_host import McpHost


@dataclass(frozen=True)
class BiddingContext:
    """Per-session context for owned-ecosystem marble_bidding tools."""

    resources_root: Path
    auction_id: str
    item_id: str
    quantity: int
    seller_owner_id: str
    buyer_owner_ids: tuple[str, ...]
    seller_minimum_unit_price: float
    buyer_budget_ceiling_by_owner: dict[str, float]
    required_terms: tuple[str, ...]
    agent_owner_by_id: dict[str, str] = field(default_factory=dict)

    @property
    def participants(self) -> tuple[str, ...]:
        return (self.seller_owner_id, *self.buyer_owner_ids)

    def owner_for_agent(self, agent_id: str) -> str | None:
        return self.agent_owner_by_id.get(agent_id)


TOOL_NAMES: tuple[str, ...] = (
    "read_owned_file",
    "query_owned_table",
    "submit_bid",
    "revise_bid",
    "seller_award_bid",
    "buyer_confirm_award",
    "record_purchase_order",
    "record_seller_order",
    "get_auction_status",
    "reveal_protected_field",
)

MUTATING_TOOLS: frozenset[str] = frozenset(
    {
        "submit_bid",
        "revise_bid",
        "seller_award_bid",
        "buyer_confirm_award",
        "record_purchase_order",
        "record_seller_order",
        "reveal_protected_field",
    }
)

CONSENT_TOOLS: frozenset[str] = frozenset({"buyer_confirm_award"})

_SUBMIT_BID_REQUIRED_ARGS: tuple[str, ...] = (
    "auction_id",
    "item_id",
    "buyer_owner_id",
    "unit_price",
    "quantity",
    "terms",
)
_SELLER_AWARD_REQUIRED_ARGS: tuple[str, ...] = (
    "auction_id",
    "seller_owner_id",
    "bid_id",
)
_BUYER_CONFIRM_REQUIRED_ARGS: tuple[str, ...] = (
    "auction_id",
    "buyer_owner_id",
    "bid_id",
)
_RECORD_PO_REQUIRED_ARGS: tuple[str, ...] = (
    "auction_id",
    "buyer_owner_id",
    "seller_owner_id",
    "bid_id",
)
_RECORD_SELLER_ORDER_REQUIRED_ARGS: tuple[str, ...] = (
    "auction_id",
    "seller_owner_id",
    "buyer_owner_id",
    "bid_id",
)

ALLOWED_TABLES: frozenset[str] = frozenset(
    {
        "inventory",
        "price_book",
        "budget_ledger",
        "bid_authorizations",
        "bids",
        "auction_state",
        "purchase_orders",
        "seller_orders",
    }
)
_RESOURCE_EVIDENCE_TABLE = "resource_evidence"
_BUYER_REQUIRED_FILE = "purchase_request.md"
_BUYER_REQUIRED_TABLE = "budget_ledger"
_SELLER_REQUIRED_FILE = "listing_sheet.md"
_SELLER_REQUIRED_TABLE = "inventory"

AUCTION_STATE_COLUMNS: frozenset[str] = frozenset(
    {
        "award_json",
        "confirmation_json",
        "purchase_order_json",
        "seller_order_json",
        "protected_disclosures",
    }
)


def _string(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


def _owner_string(description: str) -> dict[str, str]:
    return _string(
        f"{description} Use exact owner/user IDs, not chat agent IDs."
    )


def _number(description: str) -> dict[str, str]:
    return {"type": "number", "description": description}


def _integer(description: str) -> dict[str, str]:
    return {"type": "integer", "description": description}


def _schema(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
) -> dict[str, Any]:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


TOOL_SCHEMAS: list[dict[str, Any]] = [
    _schema(
        "read_owned_file",
        "Read one owner-scoped bidding file.",
        {
            "owner_id": _owner_string("Owner whose file should be read."),
            "path": _string("Relative path in that owner's files directory."),
        },
        ["owner_id", "path"],
    ),
    _schema(
        "query_owned_table",
        "Read rows from one allowed owner-scoped SQLite table.",
        {
            "owner_id": _owner_string("Owner whose SQLite table should be read."),
            "table": _string("Table name to read."),
        },
        ["owner_id", "table"],
    ),
    _schema(
        "submit_bid",
        "Submit a public bid from a buyer.",
        {
            "auction_id": _string("Auction id."),
            "item_id": _string("Item id. Legacy lot_id is accepted."),
            "buyer_owner_id": _owner_string("Buyer owner submitting the bid."),
            "unit_price": _number("Per-unit bid price."),
            "quantity": _integer("Quantity bid."),
            "terms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Required public terms included in the bid.",
            },
        },
        ["auction_id", "item_id", "buyer_owner_id", "unit_price", "quantity", "terms"],
    ),
    _schema(
        "revise_bid",
        "Revise an existing public bid owned by the same buyer.",
        {
            "auction_id": {"type": "string"},
            "item_id": {"type": "string"},
            "buyer_owner_id": {"type": "string"},
            "bid_id": {"type": "string"},
            "unit_price": {"type": "number"},
            "quantity": {"type": "integer"},
            "terms": {"type": "array", "items": {"type": "string"}},
        },
        [
            "auction_id",
            "item_id",
            "buyer_owner_id",
            "bid_id",
            "unit_price",
            "quantity",
            "terms",
        ],
    ),
    _schema(
        "seller_award_bid",
        "Seller awards one public bid.",
        {
            "auction_id": _string("Auction id."),
            "seller_owner_id": _owner_string("Seller owner awarding the bid."),
            "bid_id": _string("Public bid id to award."),
        },
        ["auction_id", "seller_owner_id", "bid_id"],
    ),
    _schema(
        "buyer_confirm_award",
        "Winning buyer confirms the awarded bid.",
        {
            "auction_id": _string("Auction id."),
            "buyer_owner_id": _owner_string("Winning buyer owner confirming."),
            "bid_id": _string("Awarded bid id."),
        },
        ["auction_id", "buyer_owner_id", "bid_id"],
    ),
    _schema(
        "record_purchase_order",
        "Record the buyer-side close artifact.",
        {
            "auction_id": _string("Auction id."),
            "buyer_owner_id": _owner_string("Buyer owner recording the purchase order."),
            "seller_owner_id": _owner_string("Seller owner on the award."),
            "bid_id": _string("Confirmed bid id."),
        },
        ["auction_id", "buyer_owner_id", "seller_owner_id", "bid_id"],
    ),
    _schema(
        "record_seller_order",
        "Record the seller-side close artifact.",
        {
            "auction_id": _string("Auction id."),
            "seller_owner_id": _owner_string("Seller owner recording the order."),
            "buyer_owner_id": _owner_string("Buyer owner on the award."),
            "bid_id": _string("Confirmed bid id."),
        },
        ["auction_id", "seller_owner_id", "buyer_owner_id", "bid_id"],
    ),
    _schema(
        "get_auction_status",
        "Inspect public bids, award, confirmation, close artifacts, and disclosures.",
        {"auction_id": {"type": "string"}},
        ["auction_id"],
    ),
    _schema(
        "reveal_protected_field",
        "Record disclosure of a protected bidding field.",
        {
            "auction_id": {"type": "string"},
            "owner_id": {"type": "string"},
            "field_name": {"type": "string"},
            "value": {},
            "recipient_owner_id": {"type": "string"},
        },
        ["auction_id", "owner_id", "field_name", "value", "recipient_owner_id"],
    ),
]


def register_marble_bidding_handlers(
    host: McpHost,
    *,
    context: BiddingContext,
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
    context: BiddingContext,
) -> dict[str, Any]:
    try:
        if tool_name == "read_owned_file":
            return _read_owned_file(arguments, context)
        if tool_name == "query_owned_table":
            return _query_owned_table(arguments, context)
        if tool_name == "submit_bid":
            return _submit_bid(arguments, context)
        if tool_name == "revise_bid":
            return _revise_bid(arguments, context)
        if tool_name == "seller_award_bid":
            return _seller_award_bid(arguments, context)
        if tool_name == "buyer_confirm_award":
            return _buyer_confirm_award(arguments, context)
        if tool_name == "record_purchase_order":
            return _record_purchase_order(arguments, context)
        if tool_name == "record_seller_order":
            return _record_seller_order(arguments, context)
        if tool_name == "get_auction_status":
            return _get_auction_status(arguments, context)
        if tool_name == "reveal_protected_field":
            return _reveal_protected_field(arguments, context)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "error": "invalid_stored_json",
            "details": str(exc),
        }
    return {"ok": False, "error": f"unknown_tool:{tool_name}"}


def _owner_root(context: BiddingContext, owner_id: str) -> Path:
    return context.resources_root / "agents" / owner_id


def _db_path_for(context: BiddingContext, owner_id: str) -> Path:
    return _owner_root(context, owner_id) / "db" / "personal.sqlite"


def _open(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {str(row["name"]) for row in rows}


def _preflight_participant_dbs(
    context: BiddingContext,
    *,
    required_tables: tuple[str, ...] = (),
    required_tables_by_owner: Mapping[str, tuple[str, ...]] | None = None,
    require_auction_state: bool = False,
) -> dict[str, Any] | None:
    required_tables_by_owner = required_tables_by_owner or {}
    for owner_id in context.participants:
        db_path = _db_path_for(context, owner_id)
        if not db_path.is_file():
            return {
                "ok": False,
                "error": "participant_db_missing",
                "owner_id": owner_id,
            }
        conn = _open(db_path)
        try:
            expected = set(required_tables)
            expected.update(required_tables_by_owner.get(owner_id, ()))
            missing_tables = sorted(expected - _table_names(conn))
            if missing_tables:
                return {
                    "ok": False,
                    "error": "participant_table_missing",
                    "owner_id": owner_id,
                    "missing_tables": missing_tables,
                }
            if require_auction_state:
                row = conn.execute(
                    "SELECT 1 FROM auction_state WHERE auction_id = ?",
                    (context.auction_id,),
                ).fetchone()
                if row is None:
                    return {
                        "ok": False,
                        "error": "auction_state_missing",
                        "owner_id": owner_id,
                    }
        finally:
            conn.close()
    return None


def _mutate_participant_dbs(
    context: BiddingContext,
    *,
    required_tables: tuple[str, ...] = (),
    required_tables_by_owner: Mapping[str, tuple[str, ...]] | None = None,
    require_auction_state: bool = False,
    mutation,
) -> dict[str, Any] | None:
    required_tables_by_owner = required_tables_by_owner or {}
    db_paths: dict[str, Path] = {}
    for owner_id in context.participants:
        db_path = _db_path_for(context, owner_id)
        if not db_path.is_file():
            return {
                "ok": False,
                "error": "participant_db_missing",
                "owner_id": owner_id,
            }
        db_paths[owner_id] = db_path

    aliases = {
        owner_id: ("main" if index == 0 else f"participant_{index}")
        for index, owner_id in enumerate(context.participants)
    }
    first_owner = context.participants[0]
    conn = _open(db_paths[first_owner])
    conn.isolation_level = None
    try:
        for owner_id in context.participants[1:]:
            conn.execute(
                f"ATTACH DATABASE ? AS {aliases[owner_id]}",
                (str(db_paths[owner_id]),),
            )
        for owner_id, schema in aliases.items():
            expected = set(required_tables)
            expected.update(required_tables_by_owner.get(owner_id, ()))
            rows = conn.execute(
                f"SELECT name FROM {schema}.sqlite_master WHERE type = 'table'"
            ).fetchall()
            table_names = {str(row["name"]) for row in rows}
            missing_tables = sorted(expected - table_names)
            if missing_tables:
                return {
                    "ok": False,
                    "error": "participant_table_missing",
                    "owner_id": owner_id,
                    "missing_tables": missing_tables,
                }
            if require_auction_state:
                row = conn.execute(
                    f"SELECT 1 FROM {schema}.auction_state WHERE auction_id = ?",
                    (context.auction_id,),
                ).fetchone()
                if row is None:
                    return {
                        "ok": False,
                        "error": "auction_state_missing",
                        "owner_id": owner_id,
                    }
        conn.execute("BEGIN IMMEDIATE")
        try:
            for owner_id, schema in aliases.items():
                mutation(owner_id, conn, schema)
            conn.execute("COMMIT")
        except Exception as exc:
            conn.execute("ROLLBACK")
            return {"ok": False, "error": "db_write_failed", "details": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": "db_write_failed", "details": str(exc)}
    finally:
        conn.close()
    return None


def _auction_matches(arguments: Mapping[str, Any], context: BiddingContext) -> bool:
    auction_id = str(arguments.get("auction_id") or "").strip()
    return auction_id == context.auction_id


def _first_argument(
    arguments: Mapping[str, Any],
    *names: str,
) -> Any:
    for name in names:
        if name in arguments and arguments[name] is not None:
            value = arguments[name]
            if not isinstance(value, str) or value.strip():
                return value
    return None


def _caller_owner(
    arguments: Mapping[str, Any],
    context: BiddingContext,
) -> str | None:
    agent_id = str(arguments.get("_agent_id") or "").strip()
    if not agent_id:
        return None
    return context.owner_for_agent(agent_id)


def _owner_from_value(value: Any, context: BiddingContext) -> str:
    owner_or_agent = str(value or "").strip()
    if not owner_or_agent:
        return ""
    if owner_or_agent in context.participants:
        return owner_or_agent
    return context.owner_for_agent(owner_or_agent) or owner_or_agent


def _owner_from_fields(
    arguments: Mapping[str, Any],
    context: BiddingContext,
    *field_names: str,
) -> str:
    return _owner_from_value(_first_argument(arguments, *field_names), context)


def _buyer_owner_argument(
    arguments: Mapping[str, Any],
    context: BiddingContext,
) -> str:
    owner_id = _owner_from_fields(
        arguments,
        context,
        "buyer_owner_id",
        "buyer_id",
        "owner_id",
    )
    if owner_id:
        return owner_id
    caller = _caller_owner(arguments, context)
    if caller in context.buyer_owner_ids:
        return caller
    return ""


def _seller_owner_argument(
    arguments: Mapping[str, Any],
    context: BiddingContext,
) -> str:
    owner_id = _owner_from_fields(
        arguments,
        context,
        "seller_owner_id",
        "seller_id",
        "owner_id",
    )
    if owner_id:
        return owner_id
    caller = _caller_owner(arguments, context)
    if caller == context.seller_owner_id:
        return caller
    return ""


def _item_id_argument(
    arguments: Mapping[str, Any],
    context: BiddingContext,
) -> str:
    return str(_first_argument(arguments, "item_id") or "").strip()


def _item_matches(arguments: Mapping[str, Any], context: BiddingContext) -> bool:
    return _item_id_argument(arguments, context) == context.item_id


def _require_caller_owner(
    arguments: Mapping[str, Any],
    context: BiddingContext,
    owner_id: str,
    *,
    field_name: str,
) -> dict[str, Any] | None:
    agent_id = str(arguments.get("_agent_id") or "").strip()
    if not agent_id:
        return None
    caller_owner = context.owner_for_agent(agent_id)
    if caller_owner is None:
        return {
            "ok": False,
            "error": "agent_not_in_auction",
            "agent_id": agent_id,
        }
    if caller_owner != owner_id:
        return {
            "ok": False,
            "error": "caller_owner_mismatch",
            "field": field_name,
            "expected_owner_id": caller_owner,
            "received_owner_id": owner_id,
        }
    return None


def _read_owned_file(
    arguments: Mapping[str, Any],
    context: BiddingContext,
) -> dict[str, Any]:
    owner_id = _owner_from_fields(arguments, context, "owner_id")
    if not owner_id:
        owner_id = _caller_owner(arguments, context) or ""
    rel_path = str(
        arguments.get("path")
        or arguments.get("file_name")
        or arguments.get("relative_path")
        or ""
    ).strip()
    if not rel_path:
        rel_path = _default_file_for_owner(context, owner_id)
    if owner_id not in context.participants:
        return {"ok": False, "error": "owner_not_in_auction"}
    error = _require_caller_owner(
        arguments,
        context,
        owner_id,
        field_name="owner_id",
    )
    if error is not None:
        return error
    if not rel_path or rel_path.startswith("/") or ".." in Path(rel_path).parts:
        return {"ok": False, "error": "invalid_path"}
    files_root = (_owner_root(context, owner_id) / "files").resolve()
    file_path = (files_root / rel_path).resolve()
    if not file_path.is_relative_to(files_root):
        return {"ok": False, "error": "invalid_path"}
    if not file_path.is_file():
        return {"ok": False, "error": "file_not_found"}
    _record_resource_evidence(context, owner_id, kind="file", name=rel_path)
    return {
        "ok": True,
        "owner_id": owner_id,
        "path": rel_path,
        "content": file_path.read_text(encoding="utf-8"),
    }


def _query_owned_table(
    arguments: Mapping[str, Any],
    context: BiddingContext,
) -> dict[str, Any]:
    owner_id = _owner_from_fields(arguments, context, "owner_id")
    if not owner_id:
        owner_id = _caller_owner(arguments, context) or ""
    table = str(arguments.get("table") or arguments.get("table_name") or "").strip()
    if not table:
        table = _default_table_for_owner(context, owner_id)
    if owner_id not in context.participants:
        return {"ok": False, "error": "owner_not_in_auction"}
    error = _require_caller_owner(
        arguments,
        context,
        owner_id,
        field_name="owner_id",
    )
    if error is not None:
        return error
    if table not in ALLOWED_TABLES:
        return {"ok": False, "error": "table_not_allowed"}
    db_path = _db_path_for(context, owner_id)
    if not db_path.is_file():
        return {"ok": False, "error": "db_not_found"}
    conn = _open(db_path)
    try:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    finally:
        conn.close()
    _record_resource_evidence(context, owner_id, kind="table", name=table)
    return {
        "ok": True,
        "owner_id": owner_id,
        "table": table,
        "rows": [dict(row) for row in rows],
    }


def _record_resource_evidence(
    context: BiddingContext,
    owner_id: str,
    *,
    kind: str,
    name: str,
) -> None:
    db_path = _db_path_for(context, owner_id)
    if not db_path.is_file():
        return
    conn = _open(db_path)
    try:
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {_RESOURCE_EVIDENCE_TABLE} "
            "(kind TEXT NOT NULL, name TEXT NOT NULL, "
            "PRIMARY KEY (kind, name))"
        )
        conn.execute(
            f"INSERT OR IGNORE INTO {_RESOURCE_EVIDENCE_TABLE} (kind, name) "
            "VALUES (?, ?)",
            (kind, name),
        )
        conn.commit()
    finally:
        conn.close()


def _resource_evidence(context: BiddingContext, owner_id: str) -> set[tuple[str, str]]:
    db_path = _db_path_for(context, owner_id)
    if not db_path.is_file():
        return set()
    conn = _open(db_path)
    try:
        if _RESOURCE_EVIDENCE_TABLE not in _table_names(conn):
            return set()
        rows = conn.execute(
            f"SELECT kind, name FROM {_RESOURCE_EVIDENCE_TABLE}"
        ).fetchall()
        return {(str(row["kind"]), str(row["name"])) for row in rows}
    finally:
        conn.close()


def _resource_step(tool: str, args: dict[str, str]) -> dict[str, Any]:
    return {"tool": tool, "args": args}


def _missing_buyer_resource_evidence_error(
    context: BiddingContext,
    buyer_owner_id: str,
) -> dict[str, Any] | None:
    evidence = _resource_evidence(context, buyer_owner_id)
    steps: list[dict[str, Any]] = []
    if ("file", _BUYER_REQUIRED_FILE) not in evidence:
        steps.append(
            _resource_step(
                "read_owned_file",
                {"owner_id": buyer_owner_id, "path": _BUYER_REQUIRED_FILE},
            )
        )
    if ("table", _BUYER_REQUIRED_TABLE) not in evidence:
        steps.append(
            _resource_step(
                "query_owned_table",
                {"owner_id": buyer_owner_id, "table": _BUYER_REQUIRED_TABLE},
            )
        )
    if not steps:
        return None
    return _missing_resource_evidence_error(
        owner_id=buyer_owner_id,
        next_actor="buyer",
        retry_tool="submit_bid",
        steps=steps,
    )


def _missing_seller_resource_evidence_error(
    context: BiddingContext,
    seller_owner_id: str,
) -> dict[str, Any] | None:
    evidence = _resource_evidence(context, seller_owner_id)
    steps: list[dict[str, Any]] = []
    if ("file", _SELLER_REQUIRED_FILE) not in evidence:
        steps.append(
            _resource_step(
                "read_owned_file",
                {"owner_id": seller_owner_id, "path": _SELLER_REQUIRED_FILE},
            )
        )
    if ("table", _SELLER_REQUIRED_TABLE) not in evidence:
        steps.append(
            _resource_step(
                "query_owned_table",
                {"owner_id": seller_owner_id, "table": _SELLER_REQUIRED_TABLE},
            )
        )
    if not steps:
        return None
    return _missing_resource_evidence_error(
        owner_id=seller_owner_id,
        next_actor="seller",
        retry_tool="seller_award_bid",
        steps=steps,
    )


def _missing_resource_evidence_error(
    *,
    owner_id: str,
    next_actor: str,
    retry_tool: str,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "missing_resource_evidence",
        "owner_id": owner_id,
        "missing_resource_steps": steps,
        "next_required_action": {
            "next_actor": next_actor,
            "next_tool": steps[0]["tool"],
            "resource_steps": steps,
            "retry_tool_after_resources": retry_tool,
            "instruction": (
                "Use the listed owned-resource tools first, then retry the "
                f"{retry_tool} call with canonical arguments."
            ),
        },
    }


def _default_file_for_owner(context: BiddingContext, owner_id: str) -> str:
    if owner_id == context.seller_owner_id:
        return _SELLER_REQUIRED_FILE
    if owner_id in context.buyer_owner_ids:
        return _BUYER_REQUIRED_FILE
    return ""


def _default_table_for_owner(context: BiddingContext, owner_id: str) -> str:
    if owner_id == context.seller_owner_id:
        return _SELLER_REQUIRED_TABLE
    if owner_id in context.buyer_owner_ids:
        return _BUYER_REQUIRED_TABLE
    return ""


def _all_bids(context: BiddingContext) -> list[dict[str, Any]]:
    db_path = _db_path_for(context, context.seller_owner_id)
    if not db_path.is_file():
        return []
    conn = _open(db_path)
    try:
        rows = conn.execute(
            "SELECT bid_id, auction_id, item_id, buyer_owner_id, unit_price, "
            "quantity, terms_json, status, order_index FROM bids "
            "WHERE auction_id = ? AND item_id = ? ORDER BY order_index",
            (context.auction_id, context.item_id),
        ).fetchall()
        bids = []
        for row in rows:
            bid = dict(row)
            bid["terms"] = json.loads(bid.pop("terms_json"))
            bids.append(bid)
        return bids
    finally:
        conn.close()


def _find_bid(context: BiddingContext, bid_id: str) -> dict[str, Any] | None:
    for bid in _all_bids(context):
        if bid["bid_id"] == bid_id:
            return bid
    return None


def _next_bid_index(context: BiddingContext) -> tuple[int, dict[str, Any] | None]:
    error = _preflight_participant_dbs(context, required_tables=("bids",))
    if error is not None:
        return 0, error
    conn = _open(_db_path_for(context, context.seller_owner_id))
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(order_index), 0) FROM bids",
        ).fetchone()
        return int(row[0]) + 1, None
    finally:
        conn.close()


def _write_bid_everywhere(
    context: BiddingContext,
    bid: dict[str, Any],
    *,
    replace: bool,
) -> dict[str, Any] | None:
    def mutation(owner_id: str, conn: sqlite3.Connection, schema: str) -> None:
        values = (
            bid["bid_id"],
            bid["auction_id"],
            bid["item_id"],
            bid["buyer_owner_id"],
            bid["unit_price"],
            bid["quantity"],
            json.dumps(bid["terms"]),
            bid["status"],
            bid["order_index"],
        )
        if replace:
            cursor = conn.execute(
                f"UPDATE {schema}.bids SET auction_id = ?, item_id = ?, buyer_owner_id = ?, "
                "unit_price = ?, quantity = ?, terms_json = ?, status = ?, "
                "order_index = ? WHERE bid_id = ? AND auction_id = ? "
                "AND item_id = ? AND buyer_owner_id = ?",
                (
                    bid["auction_id"],
                    bid["item_id"],
                    bid["buyer_owner_id"],
                    bid["unit_price"],
                    bid["quantity"],
                    json.dumps(bid["terms"]),
                    bid["status"],
                    bid["order_index"],
                    bid["bid_id"],
                    bid["auction_id"],
                    bid["item_id"],
                    bid["buyer_owner_id"],
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"bid_missing:{owner_id}:{bid['bid_id']}")
        else:
            conn.execute(
                f"INSERT INTO {schema}.bids (bid_id, auction_id, item_id, buyer_owner_id, "
                "unit_price, quantity, terms_json, status, order_index) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )

    return _mutate_participant_dbs(
        context,
        required_tables=("bids",),
        mutation=mutation,
    )


def _update_auction_state_everywhere(
    context: BiddingContext,
    *,
    column: str,
    value: Any,
) -> dict[str, Any] | None:
    if column not in AUCTION_STATE_COLUMNS:
        raise ValueError(f"unknown auction_state column: {column}")
    encoded = json.dumps(value)

    def mutation(owner_id: str, conn: sqlite3.Connection, schema: str) -> None:
        cursor = conn.execute(
            f"UPDATE {schema}.auction_state SET {column} = ? WHERE auction_id = ?",
            (encoded, context.auction_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"auction_state_missing:{owner_id}")

    return _mutate_participant_dbs(
        context,
        required_tables=("auction_state",),
        require_auction_state=True,
        mutation=mutation,
    )


def _parse_positive_float(
    value: Any,
    *,
    error: str,
) -> tuple[float, dict[str, Any] | None]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0, {"ok": False, "error": error}
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        return 0.0, {"ok": False, "error": error}
    return parsed, None


def _parse_quantity(value: Any) -> tuple[int, dict[str, Any] | None]:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return 0, {"ok": False, "error": "invalid_quantity"}
    return value, None


def _parse_terms(
    value: Any,
    context: BiddingContext,
) -> tuple[list[str], dict[str, Any] | None]:
    if isinstance(value, str):
        raw_terms = [
            item.strip()
            for chunk in value.splitlines()
            for item in chunk.replace(";", ",").split(",")
        ]
        value = [item for item in raw_terms if item]
    if not isinstance(value, (list, tuple)):
        return [], {"ok": False, "error": "invalid_terms"}
    if any(not isinstance(term, str) for term in value):
        return [], {"ok": False, "error": "invalid_terms"}
    terms = [term.strip() for term in value]
    if any(not term for term in terms):
        return [], {"ok": False, "error": "invalid_terms"}
    missing_terms = [term for term in context.required_terms if term not in terms]
    if missing_terms:
        return terms, {
            "ok": False,
            "error": "required_terms_missing",
            "missing_terms": missing_terms,
        }
    return terms, None


def _missing_required_arguments(
    arguments: Mapping[str, Any],
    required: tuple[str, ...],
) -> list[str]:
    missing: list[str] = []
    for name in required:
        if name not in arguments:
            missing.append(name)
            continue
        value = arguments.get(name)
        if value is None:
            missing.append(name)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(name)
    return missing


def _missing_required_error(
    arguments: Mapping[str, Any],
    required: tuple[str, ...],
) -> dict[str, Any] | None:
    missing = _missing_required_arguments(arguments, required)
    if not missing:
        return None
    return {
        "ok": False,
        "error": "missing_required_arguments",
        "missing": missing,
        "required_args": list(required),
    }


def _quantity_argument(arguments: Mapping[str, Any], context: BiddingContext) -> Any:
    return _first_argument(arguments, "quantity")


def _unit_price_argument(
    arguments: Mapping[str, Any],
    context: BiddingContext,
    *,
    buyer_owner_id: str | None,
) -> Any:
    for name in (
        "unit_price",
    ):
        value = _first_argument(arguments, name)
        if value is not None:
            return value
    return None


def _terms_argument(arguments: Mapping[str, Any], context: BiddingContext) -> Any:
    return arguments.get("terms")


def _next_required_action(
    *,
    next_actor: str,
    next_tool: str,
    required_args: tuple[str, ...] = (),
    instruction: str,
) -> dict[str, Any]:
    out = {
        "next_actor": next_actor,
        "next_tool": next_tool,
        "instruction": instruction,
    }
    if required_args:
        out["required_args"] = list(required_args)
    return out


def _best_awardable_bid(
    context: BiddingContext,
    *,
    buyer_owner_id: str | None = None,
) -> dict[str, Any] | None:
    candidates = [
        bid
        for bid in _all_bids(context)
        if bid.get("status") in {"active", "revised"}
        and float(bid.get("unit_price", 0.0)) >= context.seller_minimum_unit_price
        and (buyer_owner_id is None or bid.get("buyer_owner_id") == buyer_owner_id)
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda bid: (
            float(bid["unit_price"]),
            -int(bid.get("order_index", 0)),
        ),
    )


def _distinct_public_bidder_count(context: BiddingContext) -> int:
    return len(
        {
            str(bid.get("buyer_owner_id") or "")
            for bid in _all_bids(context)
            if bid.get("status") in {"active", "revised"}
        }
    )


def _public_bidder_owner_ids(context: BiddingContext) -> set[str]:
    return {
        str(bid.get("buyer_owner_id") or "")
        for bid in _all_bids(context)
        if bid.get("status") in {"active", "revised"}
    }


def _agent_id_for_owner(context: BiddingContext, owner_id: str) -> str | None:
    for agent_id, candidate_owner in context.agent_owner_by_id.items():
        if candidate_owner == owner_id:
            return agent_id
    return None


def _missing_bidder_fields(context: BiddingContext) -> dict[str, list[str]]:
    bidder_owners = _public_bidder_owner_ids(context)
    missing_owner_ids = [
        owner_id for owner_id in context.buyer_owner_ids if owner_id not in bidder_owners
    ]
    missing_agent_ids = [
        agent_id
        for owner_id in missing_owner_ids
        if (agent_id := _agent_id_for_owner(context, owner_id)) is not None
    ]
    return {
        "missing_buyer_owner_ids": missing_owner_ids,
        "missing_buyer_agent_ids": missing_agent_ids,
    }


def _award_record(context: BiddingContext) -> dict[str, Any] | None:
    award = _auction_state(context).get("award_json")
    return award if isinstance(award, dict) else None


def _confirmation_record(context: BiddingContext) -> dict[str, Any] | None:
    confirmation = _auction_state(context).get("confirmation_json")
    return confirmation if isinstance(confirmation, dict) else None


def _purchase_order_record(context: BiddingContext) -> dict[str, Any] | None:
    purchase_order = _auction_state(context).get("purchase_order_json")
    return purchase_order if isinstance(purchase_order, dict) else None


def _close_state_feedback(context: BiddingContext) -> dict[str, Any]:
    state = _auction_state(context)
    award = state.get("award_json")
    confirmation = state.get("confirmation_json")
    purchase_order = state.get("purchase_order_json")
    seller_order = state.get("seller_order_json")
    if isinstance(seller_order, dict):
        return {
            "close_state": "seller_order_recorded",
            "next_required_action": _next_required_action(
                next_actor="all_participants",
                next_tool="done",
                instruction=(
                    "Seller order is recorded. Emit {\"done\": true}; do not "
                    "send another chat summary first."
                ),
            ),
        }
    if isinstance(purchase_order, dict):
        return {
            "close_state": "purchase_order_recorded",
            "next_required_action": _next_required_action(
                next_actor="seller",
                next_tool="record_seller_order",
                required_args=_RECORD_SELLER_ORDER_REQUIRED_ARGS,
                instruction=(
                    "Seller must call record_seller_order with the award identifiers "
                    "from the confirmed purchase order before saying the auction is finalized."
                ),
            ),
        }
    if isinstance(confirmation, dict):
        return {
            "close_state": "award_confirmed",
            "next_required_action": _next_required_action(
                next_actor="winning_buyer",
                next_tool="record_purchase_order",
                required_args=_RECORD_PO_REQUIRED_ARGS,
                instruction=(
                    "Winning buyer must call record_purchase_order with the "
                    "confirmed award identifiers, then tell the seller the purchase "
                    "order is recorded."
                ),
            ),
        }
    if isinstance(award, dict):
        return {
            "close_state": "bid_awarded",
            "next_required_action": _next_required_action(
                next_actor="winning_buyer",
                next_tool="buyer_confirm_award",
                required_args=_BUYER_CONFIRM_REQUIRED_ARGS,
                instruction=(
                    "Winning buyer must call buyer_confirm_award with the awarded "
                    "bid identifiers before recording the purchase order."
                ),
            ),
        }
    best_bid = _best_awardable_bid(context)
    if best_bid is not None:
        distinct_bidder_count = _distinct_public_bidder_count(context)
        if distinct_bidder_count < 2:
            missing = _missing_bidder_fields(context)
            action = _next_required_action(
                next_actor="buyers",
                next_tool="submit_bid",
                required_args=_SUBMIT_BID_REQUIRED_ARGS,
                instruction=(
                    "At least two buyer owners must submit public bids before "
                    "award. Contact the missing buyer agents directly and wait "
                    "for their submit_bid calls."
                ),
            )
            action.update(missing)
            return {
                "close_state": "awaiting_bids",
                "distinct_bidder_count": distinct_bidder_count,
                "required_min_bidders": 2,
                **missing,
                "next_required_action": action,
            }
        return {
            "close_state": "bids_ready",
            "distinct_bidder_count": distinct_bidder_count,
            "required_min_bidders": 2,
            "next_required_action": _next_required_action(
                next_actor="seller",
                next_tool="seller_award_bid",
                required_args=_SELLER_AWARD_REQUIRED_ARGS,
                instruction="Seller should award an acceptable public bid.",
            ),
        }
    missing = _missing_bidder_fields(context)
    action = _next_required_action(
        next_actor="buyers",
        next_tool="submit_bid",
        required_args=_SUBMIT_BID_REQUIRED_ARGS,
        instruction=(
            "At least two buyer owners must submit public bids before award. "
            "Contact the missing buyer agents directly and wait for their "
            "submit_bid calls."
        ),
    )
    action.update(missing)
    return {
        "close_state": "awaiting_bids",
        **missing,
        "next_required_action": action,
    }


def _submit_bid(
    arguments: Mapping[str, Any],
    context: BiddingContext,
) -> dict[str, Any]:
    required_error = _missing_required_error(arguments, _SUBMIT_BID_REQUIRED_ARGS)
    if required_error is not None:
        return required_error
    auction_id = str(arguments.get("auction_id") or "").strip()
    item_id = _item_id_argument(arguments, context)
    buyer = _buyer_owner_argument(arguments, context)
    unit_price = _unit_price_argument(
        arguments,
        context,
        buyer_owner_id=buyer,
    )
    quantity = _quantity_argument(arguments, context)
    if auction_id != context.auction_id or item_id != context.item_id:
        return {
            "ok": False,
            "error": "auction_or_item_mismatch",
            "expected_auction_id": context.auction_id,
            "expected_item_id": context.item_id,
            "received_auction_id": auction_id,
            "received_item_id": item_id,
            "next_required_action": {
                "next_actor": "buyer",
                "next_tool": "submit_bid",
                "required_args": list(_SUBMIT_BID_REQUIRED_ARGS),
                "instruction": (
                    "Retry submit_bid with exact auction_id and item_id from "
                    "your owned request and the seller's listing."
                ),
            },
        }
    if buyer not in context.buyer_owner_ids:
        return {"ok": False, "error": "buyer_not_in_auction"}
    error = _require_caller_owner(
        arguments,
        context,
        buyer,
        field_name="buyer_owner_id",
    )
    if error is not None:
        return error
    error = _missing_buyer_resource_evidence_error(context, buyer)
    if error is not None:
        return error
    parsed_price, error = _parse_positive_float(
        unit_price,
        error="invalid_unit_price",
    )
    if error is not None:
        return error
    parsed_quantity, error = _parse_quantity(quantity)
    if error is not None:
        return error
    if parsed_quantity != context.quantity:
        return {"ok": False, "error": "quantity_mismatch"}
    parsed_terms, error = _parse_terms(_terms_argument(arguments, context), context)
    if error is not None:
        return {
            **error,
            "required_terms": list(context.required_terms),
            "next_required_action": {
                "next_actor": "buyer",
                "next_tool": "submit_bid",
                "required_args": list(_SUBMIT_BID_REQUIRED_ARGS),
                "instruction": (
                    "Retry submit_bid with terms as exact required term strings "
                    "from owned purchase-request or listing resources."
                ),
            },
        }
    order_index, error = _next_bid_index(context)
    if error is not None:
        return error
    bid = {
        "bid_id": f"bid-{order_index}",
        "auction_id": auction_id,
        "item_id": item_id,
        "buyer_owner_id": buyer,
        "unit_price": parsed_price,
        "quantity": parsed_quantity,
        "terms": parsed_terms,
        "status": "active",
        "order_index": order_index,
    }
    error = _write_bid_everywhere(context, bid, replace=False)
    if error is not None:
        return error
    return {"ok": True, "status": "bid_submitted", "bid": bid}


def _revise_bid(
    arguments: Mapping[str, Any],
    context: BiddingContext,
) -> dict[str, Any]:
    required_error = _missing_required_error(
        arguments,
        (*_SUBMIT_BID_REQUIRED_ARGS, "bid_id"),
    )
    if required_error is not None:
        return required_error
    if not _auction_matches(arguments, context) or not _item_matches(arguments, context):
        return {"ok": False, "error": "auction_or_item_mismatch"}
    bid_id = str(arguments.get("bid_id") or "").strip()
    buyer = _buyer_owner_argument(arguments, context)
    old = _find_bid(context, bid_id)
    if old is None:
        return {"ok": False, "error": "bid_not_found"}
    if old["buyer_owner_id"] != buyer:
        return {"ok": False, "error": "buyer_did_not_own_bid"}
    error = _require_caller_owner(
        arguments,
        context,
        buyer,
        field_name="buyer_owner_id",
    )
    if error is not None:
        return error
    error = _missing_buyer_resource_evidence_error(context, buyer)
    if error is not None:
        return error
    parsed_price, error = _parse_positive_float(
        _unit_price_argument(arguments, context, buyer_owner_id=buyer)
        or old["unit_price"],
        error="invalid_unit_price",
    )
    if error is not None:
        return error
    parsed_quantity, error = _parse_quantity(
        _quantity_argument(arguments, context)
    )
    if error is not None:
        return error
    if parsed_quantity != context.quantity:
        return {"ok": False, "error": "quantity_mismatch"}
    parsed_terms, error = _parse_terms(
        arguments.get("terms", old["terms"]),
        context,
    )
    if error is not None:
        return error
    revised = dict(old)
    revised["unit_price"] = parsed_price
    revised["quantity"] = parsed_quantity
    revised["terms"] = parsed_terms
    revised["status"] = "revised"
    error = _write_bid_everywhere(context, revised, replace=True)
    if error is not None:
        return error
    return {"ok": True, "status": "bid_revised", "bid": revised}


def _seller_award_bid(
    arguments: Mapping[str, Any],
    context: BiddingContext,
) -> dict[str, Any]:
    required_error = _missing_required_error(arguments, _SELLER_AWARD_REQUIRED_ARGS)
    if required_error is not None:
        return required_error
    if not _auction_matches(arguments, context):
        return {"ok": False, "error": "auction_mismatch"}
    seller = _seller_owner_argument(arguments, context)
    bid_id = str(arguments.get("bid_id") or "").strip()
    if seller != context.seller_owner_id:
        return {"ok": False, "error": "seller_not_in_auction"}
    error = _require_caller_owner(
        arguments,
        context,
        seller,
        field_name="seller_owner_id",
    )
    if error is not None:
        return error
    distinct_bidder_count = _distinct_public_bidder_count(context)
    if distinct_bidder_count < 2:
        feedback = _close_state_feedback(context)
        return {
            "ok": False,
            "error": "not_enough_distinct_bidders",
            "distinct_bidder_count": distinct_bidder_count,
            "required_min_bidders": 2,
            "missing_buyer_owner_ids": feedback.get("missing_buyer_owner_ids", []),
            "missing_buyer_agent_ids": feedback.get("missing_buyer_agent_ids", []),
            "next_required_action": feedback["next_required_action"],
            "close_state": feedback["close_state"],
        }
    bid = _find_bid(context, bid_id)
    if bid is None:
        return {
            "ok": False,
            "error": "bid_not_found",
            "public_bids": _public_bid_summaries(context),
            "next_required_action": _next_required_action(
                next_actor="seller",
                next_tool="seller_award_bid",
                required_args=_SELLER_AWARD_REQUIRED_ARGS,
                instruction=(
                    "Use one of the listed public bid_id values from public_bids, "
                    "then retry seller_award_bid."
                ),
            ),
        }
    error = _missing_seller_resource_evidence_error(context, seller)
    if error is not None:
        return error
    price = float(bid["unit_price"])
    if price < context.seller_minimum_unit_price:
        return {"ok": False, "error": "price_below_seller_minimum"}
    award = {
        "auction_id": context.auction_id,
        "item_id": context.item_id,
        "seller_owner_id": seller,
        "buyer_owner_id": bid["buyer_owner_id"],
        "bid_id": bid["bid_id"],
        "unit_price": price,
        "quantity": int(bid["quantity"]),
        "terms": bid["terms"],
    }
    error = _update_auction_state_everywhere(
        context,
        column="award_json",
        value=award,
    )
    if error is not None:
        return error
    return {"ok": True, "status": "bid_awarded", "award": award}


def _public_bid_summaries(context: BiddingContext) -> list[dict[str, Any]]:
    return [
        {
            "bid_id": str(bid.get("bid_id") or ""),
            "buyer_owner_id": str(bid.get("buyer_owner_id") or ""),
            "unit_price": float(bid.get("unit_price") or 0.0),
            "quantity": int(bid.get("quantity") or 0),
            "status": str(bid.get("status") or ""),
        }
        for bid in _all_bids(context)
    ]


def _auction_state(context: BiddingContext) -> dict[str, Any]:
    db_path = _db_path_for(context, context.seller_owner_id)
    if not db_path.is_file():
        return {"protected_disclosures": []}
    conn = _open(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM auction_state WHERE auction_id = ?",
            (context.auction_id,),
        ).fetchone()
        if row is None:
            return {"protected_disclosures": []}
        out = dict(row)
        for key in (
            "award_json",
            "confirmation_json",
            "purchase_order_json",
            "seller_order_json",
            "protected_disclosures",
        ):
            if out.get(key):
                out[key] = json.loads(out[key])
            else:
                out[key] = [] if key == "protected_disclosures" else None
        return out
    finally:
        conn.close()


def _buyer_confirm_award(
    arguments: Mapping[str, Any],
    context: BiddingContext,
) -> dict[str, Any]:
    required_error = _missing_required_error(arguments, _BUYER_CONFIRM_REQUIRED_ARGS)
    if required_error is not None:
        return required_error
    if not _auction_matches(arguments, context):
        return {"ok": False, "error": "auction_mismatch"}
    buyer = _buyer_owner_argument(arguments, context)
    bid_id = str(arguments.get("bid_id") or "").strip()
    award = _award_record(context)
    if buyer not in context.buyer_owner_ids:
        return {"ok": False, "error": "buyer_not_in_auction"}
    error = _require_caller_owner(
        arguments,
        context,
        buyer,
        field_name="buyer_owner_id",
    )
    if error is not None:
        return error
    if not isinstance(award, dict) or award.get("bid_id") != bid_id:
        return {"ok": False, "error": "bid_not_awarded"}
    if award.get("buyer_owner_id") != buyer:
        return {"ok": False, "error": "buyer_did_not_win_award"}
    price = float(award["unit_price"])
    budget = context.buyer_budget_ceiling_by_owner.get(buyer)
    if budget is None:
        return {"ok": False, "error": "buyer_budget_missing"}
    if price > budget:
        return {"ok": False, "error": "price_above_buyer_budget"}
    confirmation = {
        "auction_id": context.auction_id,
        "item_id": context.item_id,
        "seller_owner_id": str(award.get("seller_owner_id") or context.seller_owner_id),
        "buyer_owner_id": buyer,
        "bid_id": bid_id,
        "unit_price": price,
        "quantity": int(award["quantity"]),
        "terms": award["terms"],
    }
    error = _update_auction_state_everywhere(
        context,
        column="confirmation_json",
        value=confirmation,
    )
    if error is not None:
        return error
    return {"ok": True, "status": "award_confirmed", "confirmation": confirmation}


def _record_purchase_order(
    arguments: Mapping[str, Any],
    context: BiddingContext,
) -> dict[str, Any]:
    required_error = _missing_required_error(arguments, _RECORD_PO_REQUIRED_ARGS)
    if required_error is not None:
        return required_error
    if not _auction_matches(arguments, context):
        return {"ok": False, "error": "auction_mismatch"}
    buyer = _buyer_owner_argument(arguments, context)
    seller = _seller_owner_argument(arguments, context)
    bid_id = str(arguments.get("bid_id") or "").strip()
    confirmation = _confirmation_record(context)
    if not isinstance(confirmation, dict) or confirmation.get("bid_id") != bid_id:
        return {
            "ok": False,
            "error": "award_not_confirmed",
            **_close_state_feedback(context),
        }
    if confirmation.get("buyer_owner_id") != buyer or seller != context.seller_owner_id:
        return {"ok": False, "error": "owner_mismatch"}
    if buyer not in context.buyer_owner_ids:
        return {"ok": False, "error": "buyer_not_in_auction"}
    error = _require_caller_owner(
        arguments,
        context,
        buyer,
        field_name="buyer_owner_id",
    )
    if error is not None:
        return error
    po = {
        "po_id": f"PO-{context.auction_id}",
        "auction_id": context.auction_id,
        "item_id": context.item_id,
        "seller_owner_id": seller,
        "buyer_owner_id": buyer,
        "bid_id": bid_id,
        "quantity": int(confirmation["quantity"]),
        "unit_price": float(confirmation["unit_price"]),
        "terms": confirmation["terms"],
    }
    encoded = json.dumps(po)

    def mutation(owner_id: str, conn: sqlite3.Connection, schema: str) -> None:
        if owner_id == buyer:
            conn.execute(
                f"INSERT INTO {schema}.purchase_orders VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    po["po_id"],
                    po["auction_id"],
                    po["item_id"],
                    po["seller_owner_id"],
                    po["buyer_owner_id"],
                    po["bid_id"],
                    po["quantity"],
                    po["unit_price"],
                    json.dumps(po["terms"]),
                ),
            )
        cursor = conn.execute(
            f"UPDATE {schema}.auction_state SET purchase_order_json = ? "
            "WHERE auction_id = ?",
            (encoded, context.auction_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"auction_state_missing:{owner_id}")

    error = _mutate_participant_dbs(
        context,
        required_tables=("auction_state",),
        required_tables_by_owner={buyer: ("purchase_orders",)},
        require_auction_state=True,
        mutation=mutation,
    )
    if error is not None:
        return error
    return {
        "ok": True,
        "status": "purchase_order_recorded",
        "purchase_order": po,
        **_close_state_feedback(context),
    }


def _record_seller_order(
    arguments: Mapping[str, Any],
    context: BiddingContext,
) -> dict[str, Any]:
    required_error = _missing_required_error(
        arguments,
        _RECORD_SELLER_ORDER_REQUIRED_ARGS,
    )
    if required_error is not None:
        return required_error
    if not _auction_matches(arguments, context):
        return {"ok": False, "error": "auction_mismatch"}
    seller = _seller_owner_argument(arguments, context)
    po = _purchase_order_record(context)
    buyer = _buyer_owner_argument(arguments, context)
    bid_id = str(arguments.get("bid_id") or "").strip()
    if not isinstance(po, dict) or po.get("bid_id") != bid_id:
        return {
            "ok": False,
            "error": "purchase_order_missing",
            **_close_state_feedback(context),
        }
    if seller != context.seller_owner_id or po.get("buyer_owner_id") != buyer:
        return {"ok": False, "error": "owner_mismatch"}
    if buyer not in context.buyer_owner_ids:
        return {"ok": False, "error": "buyer_not_in_auction"}
    error = _require_caller_owner(
        arguments,
        context,
        seller,
        field_name="seller_owner_id",
    )
    if error is not None:
        return error
    order = {
        "order_id": f"SO-{context.auction_id}",
        "auction_id": context.auction_id,
        "item_id": context.item_id,
        "seller_owner_id": seller,
        "buyer_owner_id": buyer,
        "bid_id": bid_id,
        "quantity": int(po["quantity"]),
        "unit_price": float(po["unit_price"]),
        "terms": po["terms"],
    }
    encoded = json.dumps(order)

    def mutation(owner_id: str, conn: sqlite3.Connection, schema: str) -> None:
        if owner_id == seller:
            conn.execute(
                f"INSERT INTO {schema}.seller_orders VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    order["order_id"],
                    order["auction_id"],
                    order["item_id"],
                    order["seller_owner_id"],
                    order["buyer_owner_id"],
                    order["bid_id"],
                    order["quantity"],
                    order["unit_price"],
                    json.dumps(order["terms"]),
                ),
            )
        cursor = conn.execute(
            f"UPDATE {schema}.auction_state SET seller_order_json = ? "
            "WHERE auction_id = ?",
            (encoded, context.auction_id),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"auction_state_missing:{owner_id}")

    error = _mutate_participant_dbs(
        context,
        required_tables=("auction_state",),
        required_tables_by_owner={seller: ("seller_orders",)},
        require_auction_state=True,
        mutation=mutation,
    )
    if error is not None:
        return error
    return {
        "ok": True,
        "status": "seller_order_recorded",
        "seller_order": order,
        **_close_state_feedback(context),
    }


def _get_auction_status(
    arguments: Mapping[str, Any],
    context: BiddingContext,
) -> dict[str, Any]:
    auction_id = str(arguments.get("auction_id") or context.auction_id).strip()
    if auction_id != context.auction_id:
        return {"ok": False, "error": "auction_mismatch"}
    state = _auction_state(context)
    state["protected_disclosures"] = state.get("protected_disclosures") or []
    return {
        "ok": True,
        "auction_id": context.auction_id,
        "item_id": context.item_id,
        "quantity": context.quantity,
        "bids": _all_bids(context),
        "owner_id_field_map": {
            "seller_owner_id": context.seller_owner_id,
            "buyer_owner_ids": list(context.buyer_owner_ids),
            "agent_owner_by_id": dict(context.agent_owner_by_id),
        },
        "canonical_close_sequence": [
            "buyer submit_bid",
            "seller seller_award_bid",
            "winning buyer buyer_confirm_award",
            "winning buyer record_purchase_order",
            "seller record_seller_order",
        ],
        **_close_state_feedback(context),
        **state,
    }


def _reveal_protected_field(
    arguments: Mapping[str, Any],
    context: BiddingContext,
) -> dict[str, Any]:
    if not _auction_matches(arguments, context):
        return {"ok": False, "error": "auction_mismatch"}
    owner_id = str(arguments.get("owner_id") or "").strip()
    field_name = str(arguments.get("field_name") or "").strip()
    recipient = str(arguments.get("recipient_owner_id") or "").strip()
    if owner_id not in context.participants:
        return {"ok": False, "error": "owner_not_in_auction"}
    error = _require_caller_owner(
        arguments,
        context,
        owner_id,
        field_name="owner_id",
    )
    if error is not None:
        return error
    if not field_name:
        return {"ok": False, "error": "missing_field_name"}
    if recipient not in context.participants:
        return {"ok": False, "error": "recipient_not_in_auction"}
    state = _auction_state(context)
    disclosures = state.get("protected_disclosures") or []
    record = {
        "owner_id": owner_id,
        "field_name": field_name,
        "value": arguments.get("value"),
        "recipient_owner_id": recipient,
    }
    disclosures.append(record)
    error = _update_auction_state_everywhere(
        context,
        column="protected_disclosures",
        value=disclosures,
    )
    if error is not None:
        return error
    return {"ok": True, "status": "disclosed", "record": record}
