"""Emit resource sidecar files for generated scenario bundles."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def emit_resource_manifest_files(
    resource_manifest: Mapping[str, Any] | None,
) -> dict[str, str]:
    """Return files for the optional ``resources/`` bundle directory."""
    if not resource_manifest:
        return {}
    return {
        "manifest.json": (
            json.dumps(resource_manifest, indent=2, ensure_ascii=False) + "\n"
        )
    }


def write_resource_bundle(
    resource_root: Path | str,
    resource_manifest: Mapping[str, Any] | None,
    resource_fixtures: Mapping[str, Any] | None = None,
) -> None:
    """Materialize ``resources/`` sidecars and deterministic fixtures."""
    if not resource_manifest:
        return
    root = Path(resource_root)
    root.mkdir(parents=True, exist_ok=True)
    fixtures = dict(resource_fixtures or {})

    for relative_path, contents in dict(fixtures.get("files", {})).items():
        path = _safe_resource_path(root, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(contents))

    for relative_path, spec in dict(fixtures.get("sqlite", {})).items():
        db_path = _safe_resource_path(root, relative_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path.exists():
            db_path.unlink()
        _write_sqlite_fixture(db_path, spec)

    (root / "manifest.json").write_text(
        json.dumps(resource_manifest, indent=2, ensure_ascii=False) + "\n"
    )


def _safe_resource_path(root: Path, relative_path: str) -> Path:
    rel = Path(relative_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"resource path must stay under resources/: {relative_path!r}")
    resolved = (root / rel).resolve()
    root_resolved = root.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise ValueError(f"resource path escapes resources/: {relative_path!r}")
    return resolved


def _write_sqlite_fixture(db_path: Path, spec: Any) -> None:
    if not isinstance(spec, Mapping):
        raise TypeError("sqlite fixture spec must be a mapping")
    tables = spec.get("tables", {})
    if not isinstance(tables, Mapping):
        raise TypeError("sqlite fixture 'tables' must be a mapping")
    with sqlite3.connect(db_path) as conn:
        for table_name, table_spec in tables.items():
            if not isinstance(table_spec, Mapping):
                raise TypeError("sqlite table spec must be a mapping")
            columns = table_spec.get("columns", {})
            rows = list(table_spec.get("rows", []))
            if not isinstance(columns, Mapping) or not columns:
                raise TypeError("sqlite table columns must be a non-empty mapping")
            column_sql = ", ".join(
                f"{_quote_identifier(str(name))} {str(type_decl)}"
                for name, type_decl in columns.items()
            )
            conn.execute(
                f"CREATE TABLE {_quote_identifier(str(table_name))} ({column_sql})"
            )
            column_names = [str(name) for name in columns.keys()]
            if rows:
                placeholders = ", ".join("?" for _ in column_names)
                quoted_columns = ", ".join(_quote_identifier(name) for name in column_names)
                conn.executemany(
                    (
                        f"INSERT INTO {_quote_identifier(str(table_name))} "
                        f"({quoted_columns}) VALUES ({placeholders})"
                    ),
                    [
                        tuple(dict(row).get(column_name) for column_name in column_names)
                        for row in rows
                    ],
                )


def _quote_identifier(identifier: str) -> str:
    if not identifier.replace("_", "").isalnum() or not identifier:
        raise ValueError(f"invalid SQLite identifier: {identifier!r}")
    if identifier[0].isdigit():
        raise ValueError(f"invalid SQLite identifier: {identifier!r}")
    return '"' + identifier.replace('"', '""') + '"'
