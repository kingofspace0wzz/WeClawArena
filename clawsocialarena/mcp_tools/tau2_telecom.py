"""Tau2 telecom MCP tool handlers.

Family-plan reframing of the tau2 telecom domain. A per-line change
(toggle roaming, switch plan) is only committable after the affected
line owner has explicitly consented. Charge disputes are restricted to
the primary account holder.

Handlers operate against the per-user SQLite database materialized at
``resources/users/<owner_id>/db/personal.sqlite``.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from clawsocialarena.gateway.mcp_host import McpHost


@dataclass(frozen=True)
class FamilyPlanContext:
    """Per-session context for the tau2 telecom tool surface.

    ``resources_root`` points at the materialized ``resources/``
    directory. ``primary_owner_id`` owns the account and may dispute
    any charge. ``secondary_owner_ids`` own individual lines and may
    only consent for their own line.
    """

    resources_root: Path
    account_id: str
    primary_owner_id: str
    secondary_owner_ids: tuple[str, ...] = ()

    @property
    def account_members(self) -> tuple[str, ...]:
        return (self.primary_owner_id, *self.secondary_owner_ids)


TOOL_NAMES: tuple[str, ...] = (
    "find_user_id_by_name",
    "get_user_details",
    "get_line_details",
    "list_my_lines",
    "request_line_change",
    "consent_to_line_change",
    "commit_line_change",
    "dispute_charge",
)

# Tools that mutate persisted line / charge state. Lookups
# (``find_*``, ``get_*``) do not mutate. ``request_line_change``
# records a pending change. ``commit_line_change`` applies it.
# ``dispute_charge`` mutates the charge record.
MUTATING_TOOLS: frozenset[str] = frozenset(
    {
        "request_line_change",
        "commit_line_change",
        "dispute_charge",
    }
)

# ``consent_to_line_change`` is the canonical tool-form consent: the
# affected line owner explicitly authorizes a pending change. Treated
# as a consent signal in addition to prose consent in outbound
# messages, gated on the caller being the affected line owner.
CONSENT_TOOLS: frozenset[str] = frozenset(
    {
        "consent_to_line_change",
    }
)


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "find_user_id_by_name",
        "description": "Look up a family-plan member's user_id by first name.",
        "parameters": {
            "type": "object",
            "properties": {"first_name": {"type": "string"}},
            "required": ["first_name"],
        },
    },
    {
        "type": "function",
        "name": "get_user_details",
        "description": "Return a family-plan member's public profile.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The target user_id (NOT agent_id).",
                }
            },
            "required": ["user_id"],
        },
    },
    {
        "type": "function",
        "name": "get_line_details",
        "description": (
            "Return the line's details: phone_number, plan_id, owner_id, "
            "roaming flag, pending_change, committed_change, consents."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "caller_id": {
                    "type": "string",
                    "description": (
                        "The caller's user_id (NOT agent_id). Must be a "
                        "member of the family plan."
                    ),
                },
                "line_id": {
                    "type": "string",
                    "description": "The line identifier (e.g., 'L1001').",
                },
            },
            "required": ["caller_id", "line_id"],
        },
    },
    {
        "type": "function",
        "name": "list_my_lines",
        "description": (
            "Return the lines visible to the caller from their own DB."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "caller_id": {
                    "type": "string",
                    "description": "The caller's user_id (NOT agent_id).",
                },
                "user_id": {
                    "type": "string",
                    "description": (
                        "Alias of caller_id; either is accepted. The "
                        "caller's user_id, NOT agent_id."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "request_line_change",
        "description": (
            "Record a pending line change (e.g., enable roaming). The "
            "change will not take effect until the affected line owner "
            "consents and the committer commits."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "line_id": {
                    "type": "string",
                    "description": "The line identifier (e.g., 'L1001').",
                },
                "change_kind": {
                    "type": "string",
                    "description": (
                        "The kind of change. Must be the literal string "
                        "\"toggle_roaming\" for enabling or disabling roaming "
                        "on a line."
                    ),
                },
                "new_value": {
                    "description": "The new value for the change (string or boolean).",
                },
                "requester_id": {
                    "type": "string",
                    "description": (
                        "The user_id of the family-plan member requesting "
                        "the change (NOT agent_id)."
                    ),
                },
            },
            "required": ["line_id", "change_kind", "new_value", "requester_id"],
        },
    },
    {
        "type": "function",
        "name": "consent_to_line_change",
        "description": (
            "The affected line owner explicitly authorizes the pending "
            "change. Only the line's owner can grant consent for "
            "themselves."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "line_id": {
                    "type": "string",
                    "description": "The line identifier (e.g., 'L1001').",
                },
                "consenter_id": {
                    "type": "string",
                    "description": (
                        "The user_id of the line owner granting consent "
                        "(NOT agent_id). Must equal the line's owner_id."
                    ),
                },
            },
            "required": ["line_id", "consenter_id"],
        },
    },
    {
        "type": "function",
        "name": "commit_line_change",
        "description": (
            "Commit the pending line change. The primary account holder "
            "(committer) can commit only after the affected line owner "
            "has consented."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "line_id": {
                    "type": "string",
                    "description": "The line identifier (e.g., 'L1001').",
                },
                "committer_id": {
                    "type": "string",
                    "description": (
                        "The user_id of the committing primary account "
                        "holder (NOT agent_id)."
                    ),
                },
            },
            "required": ["line_id", "committer_id"],
        },
    },
    {
        "type": "function",
        "name": "dispute_charge",
        "description": (
            "Open a dispute on a bill line. Only the primary account "
            "holder may dispute."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "bill_id": {
                    "type": "string",
                    "description": "The bill identifier.",
                },
                "requester_id": {
                    "type": "string",
                    "description": (
                        "The user_id of the primary account holder "
                        "raising the dispute (NOT agent_id)."
                    ),
                },
            },
            "required": ["bill_id", "requester_id"],
        },
    },
]


def register_tau2_telecom_handlers(
    host: McpHost,
    *,
    context: FamilyPlanContext,
) -> None:
    """Register all tau2 telecom tool handlers against the given host."""

    def make_handler(name: str):
        def _handler(arguments: dict) -> dict:
            return dispatch(name, dict(arguments), context)

        return _handler

    for tool_name in TOOL_NAMES:
        host.register(tool_name, make_handler(tool_name))


def dispatch(
    tool_name: str,
    arguments: dict,
    context: FamilyPlanContext,
) -> dict[str, Any]:
    """Dispatch a tau2 telecom tool call against the family plan."""
    if tool_name == "find_user_id_by_name":
        return _find_user_id_by_name(arguments, context)
    if tool_name == "get_user_details":
        return _get_user_details(arguments, context)
    if tool_name == "get_line_details":
        return _get_line_details(arguments, context)
    if tool_name == "list_my_lines":
        return _list_my_lines(arguments, context)
    if tool_name == "request_line_change":
        return _request_line_change(arguments, context)
    if tool_name == "consent_to_line_change":
        return _consent_to_line_change(arguments, context)
    if tool_name == "commit_line_change":
        return _commit_line_change(arguments, context)
    if tool_name == "dispute_charge":
        return _dispute_charge(arguments, context)
    return {"ok": False, "error": f"unknown_tool:{tool_name}"}


def _db_path_for(context: FamilyPlanContext, owner_id: str) -> Path:
    return context.resources_root / "users" / owner_id / "db" / "personal.sqlite"


def _open(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_line(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "line_id": row["line_id"],
        "account_id": row["account_id"],
        "owner_id": row["owner_id"],
        "phone_number": row["phone_number"],
        "plan_id": row["plan_id"],
        "roaming_enabled": bool(row["roaming_enabled"]),
        "pending_change": json.loads(row["pending_change"]) if row["pending_change"] else None,
        "committed_change": json.loads(row["committed_change"]) if row["committed_change"] else None,
        "consents": json.loads(row["consents"]) if row["consents"] else {},
    }


def _find_user_id_by_name(
    arguments: Mapping[str, Any],
    context: FamilyPlanContext,
) -> dict[str, Any]:
    first_name = str(arguments.get("first_name") or "").strip().lower()
    if not first_name:
        return {"ok": False, "error": "missing_arguments"}
    if first_name in context.account_members:
        return {
            "ok": True,
            "user_id": first_name,
            "account_id": context.account_id,
        }
    return {"ok": False, "error": "user_not_found"}


def _get_user_details(
    arguments: Mapping[str, Any],
    context: FamilyPlanContext,
) -> dict[str, Any]:
    user_id = str(arguments.get("user_id") or "").strip()
    if user_id not in context.account_members:
        return {"ok": False, "error": "user_not_in_account"}
    role = (
        "primary_account_holder"
        if user_id == context.primary_owner_id
        else "secondary_line_owner"
    )
    return {
        "ok": True,
        "user_id": user_id,
        "account_id": context.account_id,
        "role": role,
    }


def _get_line_details(
    arguments: Mapping[str, Any],
    context: FamilyPlanContext,
) -> dict[str, Any]:
    line_id = str(arguments.get("line_id") or "").strip()
    caller = str(arguments.get("caller_id") or context.primary_owner_id).strip()
    if not line_id:
        return {"ok": False, "error": "missing_line_id"}
    if caller not in context.account_members:
        return {"ok": False, "error": "caller_not_in_account"}
    db_path = _db_path_for(context, caller)
    if not db_path.is_file():
        return {"ok": False, "error": "user_db_missing"}
    conn = _open(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM lines WHERE line_id = ?", (line_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return {"ok": False, "error": "line_not_visible_to_caller"}
    return {"ok": True, "line": _row_to_line(row)}


def _list_my_lines(
    arguments: Mapping[str, Any],
    context: FamilyPlanContext,
) -> dict[str, Any]:
    """Return lines visible to the caller from their own sqlite DB.
    Required for tractable canonical-action dispatch: every line-
    mutating tool needs a ``line_id`` argument and the agent has no
    persona-provided list of line_ids to draw from.
    """
    caller = str(arguments.get("user_id") or arguments.get("caller_id") or "").strip()
    if not caller:
        return {"ok": False, "error": "missing_arguments"}
    if caller not in context.account_members:
        return {"ok": False, "error": "caller_not_in_account"}
    db_path = _db_path_for(context, caller)
    if not db_path.is_file():
        return {"ok": False, "error": "user_db_missing"}
    conn = _open(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM lines ORDER BY line_id"
        ).fetchall()
    finally:
        conn.close()
    return {
        "ok": True,
        "user_id": caller,
        "lines": [_row_to_line(row) for row in rows],
    }


def _request_line_change(
    arguments: Mapping[str, Any],
    context: FamilyPlanContext,
) -> dict[str, Any]:
    line_id = str(arguments.get("line_id") or "").strip()
    requester = str(arguments.get("requester_id") or "").strip()
    change_kind = str(arguments.get("change_kind") or "toggle_roaming").strip()
    new_value = arguments.get("new_value", True)
    if not line_id or not requester:
        return {"ok": False, "error": "missing_arguments"}
    if requester not in context.account_members:
        return {"ok": False, "error": "requester_not_in_account"}
    line_owner = _find_line_owner(context=context, line_id=line_id)
    if line_owner is None:
        return {"ok": False, "error": "line_not_found"}
    if requester != line_owner and requester != context.primary_owner_id:
        return {"ok": False, "error": "requester_cannot_change_other_line"}
    pending = {
        "kind": change_kind,
        "line_id": line_id,
        "new_value": new_value,
        "requested_by": requester,
    }
    updates = _update_line_on_visible_dbs(
        context=context,
        line_id=line_id,
        update=lambda r: ("pending_change = ?", [json.dumps(pending)]),
    )
    if updates == 0:
        return {"ok": False, "error": "line_not_found"}
    return {"ok": True, "status": "pending", "pending": pending}


def _consent_to_line_change(
    arguments: Mapping[str, Any],
    context: FamilyPlanContext,
) -> dict[str, Any]:
    line_id = str(arguments.get("line_id") or "").strip()
    consenter = str(arguments.get("consenter_id") or "").strip()
    if not line_id or not consenter:
        return {"ok": False, "error": "missing_arguments"}
    if consenter not in context.account_members:
        return {"ok": False, "error": "consenter_not_in_account"}
    line_owner = _find_line_owner(context=context, line_id=line_id)
    if line_owner is None:
        return {"ok": False, "error": "line_not_found"}
    if consenter != line_owner:
        return {"ok": False, "error": "consent_for_other_line_denied"}
    db_path = _db_path_for(context, consenter)
    conn = _open(db_path)
    try:
        row = conn.execute(
            "SELECT pending_change, consents FROM lines WHERE line_id = ?",
            (line_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return {"ok": False, "error": "line_not_found"}
    if not row["pending_change"]:
        return {"ok": False, "error": "no_pending_change"}
    consents = json.loads(row["consents"]) if row["consents"] else {}
    consents[consenter] = True
    _update_line_on_visible_dbs(
        context=context,
        line_id=line_id,
        update=lambda r: ("consents = ?", [json.dumps(consents)]),
    )
    return {"ok": True, "status": "consent_recorded", "consenter": consenter}


def _commit_line_change(
    arguments: Mapping[str, Any],
    context: FamilyPlanContext,
) -> dict[str, Any]:
    line_id = str(arguments.get("line_id") or "").strip()
    committer = str(arguments.get("committer_id") or "").strip()
    if not line_id or not committer:
        return {"ok": False, "error": "missing_arguments"}
    if committer != context.primary_owner_id:
        return {
            "ok": False,
            "error": "authorization_denied",
            "reason": "only the primary account holder may commit changes",
        }
    db_path = _db_path_for(context, context.primary_owner_id)
    conn = _open(db_path)
    try:
        row = conn.execute(
            "SELECT pending_change, consents FROM lines WHERE line_id = ?",
            (line_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return {"ok": False, "error": "line_not_found"}
    if not row["pending_change"]:
        return {"ok": False, "error": "no_pending_change"}
    pending = json.loads(row["pending_change"])
    consents = json.loads(row["consents"]) if row["consents"] else {}
    line_owner = _find_line_owner(context=context, line_id=line_id)
    if line_owner and not consents.get(line_owner):
        return {
            "ok": False,
            "error": "consent_missing",
            "line_owner_id": line_owner,
        }
    # Apply the change to the materialized roaming column if the change
    # is a roaming toggle. Otherwise just record the committed change.
    new_roaming = None
    if pending.get("kind") == "toggle_roaming":
        new_roaming = bool(pending.get("new_value", True))

    def _apply(row: sqlite3.Row) -> tuple[str, list[Any]]:
        if new_roaming is None:
            return (
                "committed_change = ?, pending_change = ?",
                [json.dumps(pending), None],
            )
        return (
            "committed_change = ?, pending_change = ?, roaming_enabled = ?",
            [json.dumps(pending), None, int(new_roaming)],
        )

    _update_line_on_visible_dbs(
        context=context,
        line_id=line_id,
        update=_apply,
    )
    return {
        "ok": True,
        "status": "finalized",
        "committed_change": pending,
        "committed_by": committer,
    }


def _dispute_charge(
    arguments: Mapping[str, Any],
    context: FamilyPlanContext,
) -> dict[str, Any]:
    """Only the primary account holder may dispute a charge."""
    requester = str(arguments.get("requester_id") or "").strip()
    bill_id = str(arguments.get("bill_id") or "").strip()
    if not requester or not bill_id:
        return {"ok": False, "error": "missing_arguments"}
    if requester != context.primary_owner_id:
        return {
            "ok": False,
            "error": "authorization_denied",
            "reason": "only the primary account holder may dispute charges",
        }
    return {"ok": True, "status": "disputed", "bill_id": bill_id, "by": requester}


def _find_line_owner(
    *,
    context: FamilyPlanContext,
    line_id: str,
) -> str | None:
    """Return the owner_id of the named line, by reading the primary's
    DB (which always carries every line on the account).
    """
    db_path = _db_path_for(context, context.primary_owner_id)
    if not db_path.is_file():
        return None
    conn = _open(db_path)
    try:
        row = conn.execute(
            "SELECT owner_id FROM lines WHERE line_id = ?", (line_id,)
        ).fetchone()
    finally:
        conn.close()
    return row["owner_id"] if row else None


def _update_line_on_visible_dbs(
    *,
    context: FamilyPlanContext,
    line_id: str,
    update,
) -> int:
    """Apply ``update`` against every account member's DB copy of the
    line. Members whose DB does not include the line are skipped
    silently (secondaries only see their own line)."""
    total = 0
    for owner_id in context.account_members:
        db_path = _db_path_for(context, owner_id)
        if not db_path.is_file():
            continue
        conn = _open(db_path)
        try:
            row = conn.execute(
                "SELECT pending_change, consents FROM lines WHERE line_id = ?",
                (line_id,),
            ).fetchone()
            if row is None:
                continue
            set_clause, values = update(row)
            cursor = conn.execute(
                f"UPDATE lines SET {set_clause} WHERE line_id = ?",
                [*values, line_id],
            )
            total += cursor.rowcount
            conn.commit()
        finally:
            conn.close()
    return total
