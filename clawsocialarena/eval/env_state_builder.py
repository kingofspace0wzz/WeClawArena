"""Build an ``EnvState`` from the post-run resource directory.

Each Phase-5 family pack lays out per-owner sqlite databases under
``resources/<role-dir>/<owner_id>/db/personal.sqlite`` (role-dir is
``pis``, ``agents``, ``passengers``, ``users``, ``team`` depending on
the pack). Tool handlers mirror writes across every participant's db
via ``_update_*_everywhere`` helpers, so any owner's db carries the
same shared rows. Reading them all and merging by primary key gives
the post-run state predicates score against.

This module is family-pack-agnostic: it discovers sqlite files under
``resources/`` recursively, reads every table, JSON-decodes columns
whose stored text parses as a JSON object/array, and merges rows by
the table's declared primary key into the dict-shape expected by
:class:`EnvState`.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from clawsocialarena.eval.predicates.types import EnvState


def build_env_state(*, resources_dir: Path | str) -> EnvState:
    """Read every ``personal.sqlite`` under ``resources_dir`` and merge
    rows into ``{table_name: {primary_key_value: row_dict}}``.

    Columns whose stored string parses as a JSON object or array are
    decoded. Empty or non-JSON strings pass through unchanged. Numeric
    and NULL columns pass through as-is.

    If two owners' dbs disagree on a column value for the same primary
    key, the last-read row wins. Handlers maintain shared state by
    writing through every participant's db, so disagreements should not
    occur in practice; if they do, the merged view is still a valid
    EnvState (predicate authors operate on a single observation).
    """
    root = Path(resources_dir)
    db: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return EnvState(db=db)
    for sqlite_path in sorted(root.glob("**/personal.sqlite")):
        _merge_db_file(sqlite_path, db)
    return EnvState(db=db)


def _merge_db_file(sqlite_path: Path, accumulator: dict[str, dict[str, Any]]) -> None:
    """Read one sqlite file and merge its tables into ``accumulator``."""
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        table_rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for table_row in table_rows:
            table_name = table_row["name"]
            pk_col = _primary_key_column(conn, table_name)
            sql = f"SELECT * FROM {table_name}"
            for row in conn.execute(sql).fetchall():
                row_dict = _decode_row(dict(row))
                if pk_col is None or pk_col not in row_dict:
                    # Tables without a primary key (e.g., availability)
                    # accumulate under a synthetic sequential index so
                    # predicates that iterate get them all. We use a
                    # negative-indexed bucket to keep them distinct from
                    # keyed rows.
                    bucket = accumulator.setdefault(table_name, {})
                    bucket[f"__row_{len(bucket)}__"] = row_dict
                    continue
                pk_value = row_dict[pk_col]
                accumulator.setdefault(table_name, {})[str(pk_value)] = row_dict
    finally:
        conn.close()


def _primary_key_column(conn: sqlite3.Connection, table_name: str) -> str | None:
    """Return the name of the single primary-key column for ``table_name``,
    or ``None`` if the table has no primary key or a composite key.
    """
    rows = list(conn.execute(f"PRAGMA table_info({table_name})").fetchall())
    pk_cols = [r["name"] for r in rows if r["pk"]]
    if len(pk_cols) == 1:
        return pk_cols[0]
    return None


def _decode_row(row: dict[str, Any]) -> dict[str, Any]:
    """JSON-decode any string column whose value parses as an object or
    array. Leave everything else unchanged.
    """
    decoded: dict[str, Any] = {}
    for key, value in row.items():
        decoded[key] = _maybe_decode_json(value)
    return decoded


def _maybe_decode_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return value
    if stripped[0] not in "{[":
        return value
    try:
        return json.loads(stripped)
    except (ValueError, TypeError):
        return value


__all__ = ["build_env_state"]
