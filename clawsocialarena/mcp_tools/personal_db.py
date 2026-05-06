"""Gateway-hosted personal database resource MCP tools."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from clawsocialarena.scenario.models import ResourceEntry, ResourceManifest


class PersonalDatabaseTool:
    """Dispatch limited ``db.*`` operations against declared SQLite resources."""

    def __init__(
        self,
        resource_root: Path | str,
        resource_manifest: ResourceManifest | dict[str, Any],
    ) -> None:
        self.resource_root = Path(resource_root).resolve()
        self.resource_manifest = ResourceManifest.model_validate(resource_manifest)

    def dispatch(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        resource_id = arguments.get("resource_id")
        if not isinstance(resource_id, str) or resource_id == "":
            return {"ok": False, "error": "missing_resource_id"}
        entry = self.resource_manifest.resources.get(resource_id)
        if entry is None:
            return {"ok": False, "error": "unknown_resource", "resource_id": resource_id}
        if not _is_authorized(entry, operation, arguments):
            return {"ok": False, "error": "forbidden", "resource_id": resource_id}
        where = _dict_arg(arguments, "where")
        values = _dict_arg(arguments, "values")
        if operation in {"db.query", "db.update", "db.delete"} and not _within_filter(
            entry, where
        ):
            return {
                "ok": False,
                "error": "row_filter_violation",
                "resource_id": resource_id,
            }
        if operation == "db.insert" and not _within_filter(entry, values):
            return {
                "ok": False,
                "error": "row_filter_violation",
                "resource_id": resource_id,
            }
        try:
            db_path = self._entry_path(entry)
            table = _table_name(entry, arguments)
        except ValueError as exc:
            return {
                "ok": False,
                "error": "invalid_resource",
                "resource_id": resource_id,
                "details": str(exc),
            }

        if operation == "db.query":
            return self._query(resource_id, db_path, table, where)
        if operation == "db.insert":
            return self._insert(resource_id, db_path, table, values)
        if operation == "db.update":
            return self._update(resource_id, db_path, table, where, values)
        if operation == "db.delete":
            return self._delete(resource_id, db_path, table, where)
        return {"ok": False, "error": "unsupported_operation", "operation": operation}

    def _entry_path(self, entry: ResourceEntry) -> Path:
        if entry.path is None:
            raise ValueError("resource has no path")
        rel = Path(entry.path)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"path escapes resources/: {entry.path!r}")
        path = (self.resource_root / rel).resolve()
        if not path.is_relative_to(self.resource_root):
            raise ValueError(f"path escapes resources/: {entry.path!r}")
        return path

    @staticmethod
    def _query(
        resource_id: str,
        db_path: Path,
        table: str,
        where: dict[str, Any],
    ) -> dict[str, Any]:
        sql, params = _select_sql(table, where)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
        return {"ok": True, "resource_id": resource_id, "rows": rows}

    @staticmethod
    def _insert(
        resource_id: str,
        db_path: Path,
        table: str,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        if not values:
            return {"ok": False, "error": "empty_values", "resource_id": resource_id}
        columns = list(values.keys())
        quoted_columns = ", ".join(_quote_identifier(column) for column in columns)
        placeholders = ", ".join("?" for _ in columns)
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                (
                    f"INSERT INTO {_quote_identifier(table)} "
                    f"({quoted_columns}) VALUES ({placeholders})"
                ),
                [values[column] for column in columns],
            )
        return {
            "ok": True,
            "resource_id": resource_id,
            "rows_affected": cursor.rowcount,
        }

    @staticmethod
    def _update(
        resource_id: str,
        db_path: Path,
        table: str,
        where: dict[str, Any],
        values: dict[str, Any],
    ) -> dict[str, Any]:
        if not values:
            return {"ok": False, "error": "empty_values", "resource_id": resource_id}
        set_sql = ", ".join(
            f"{_quote_identifier(column)} = ?" for column in values.keys()
        )
        where_sql, where_params = _where_clause(where)
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                f"UPDATE {_quote_identifier(table)} SET {set_sql}{where_sql}",
                [*values.values(), *where_params],
            )
        return {
            "ok": True,
            "resource_id": resource_id,
            "rows_affected": cursor.rowcount,
        }

    @staticmethod
    def _delete(
        resource_id: str,
        db_path: Path,
        table: str,
        where: dict[str, Any],
    ) -> dict[str, Any]:
        where_sql, where_params = _where_clause(where)
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                f"DELETE FROM {_quote_identifier(table)}{where_sql}",
                where_params,
            )
        return {
            "ok": True,
            "resource_id": resource_id,
            "rows_affected": cursor.rowcount,
        }


def _dict_arg(arguments: dict[str, Any], key: str) -> dict[str, Any]:
    value = arguments.get(key, {})
    return dict(value) if isinstance(value, dict) else {}


def _within_filter(entry: ResourceEntry, values: dict[str, Any]) -> bool:
    for key, expected in entry.row_filter.items():
        if values.get(key) != expected:
            return False
    return True


def _table_name(entry: ResourceEntry, arguments: dict[str, Any]) -> str:
    table = arguments.get("table", entry.table)
    if not isinstance(table, str) or table == "":
        raise ValueError("database resource requires a table")
    return table


def _select_sql(table: str, where: dict[str, Any]) -> tuple[str, list[Any]]:
    where_sql, where_params = _where_clause(where)
    return f"SELECT * FROM {_quote_identifier(table)}{where_sql}", where_params


def _where_clause(where: dict[str, Any]) -> tuple[str, list[Any]]:
    if not where:
        return "", []
    clauses = [f"{_quote_identifier(column)} = ?" for column in where.keys()]
    return " WHERE " + " AND ".join(clauses), list(where.values())


def _quote_identifier(identifier: str) -> str:
    if not identifier.replace("_", "").isalnum() or not identifier:
        raise ValueError(f"invalid SQLite identifier: {identifier!r}")
    if identifier[0].isdigit():
        raise ValueError(f"invalid SQLite identifier: {identifier!r}")
    return '"' + identifier.replace('"', '""') + '"'


def _is_authorized(
    entry: ResourceEntry,
    operation: str,
    arguments: dict[str, Any],
) -> bool:
    identity_id = arguments.get("identity_id")
    scope_id = arguments.get("scope_id")
    for rule in entry.allowed_operations:
        if operation not in rule.operations:
            continue
        if rule.identity_id is not None and rule.identity_id != identity_id:
            continue
        if rule.scope_id is not None and rule.scope_id != scope_id:
            continue
        return True
    return False
