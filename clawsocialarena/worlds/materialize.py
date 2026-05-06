from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from clawsocialarena.worlds.models import DatabaseResourceSpec, UserWorldPack


@dataclass(frozen=True)
class MaterializedWorldResources:
    resource_root: Path
    file_paths: dict[str, Path]
    database_paths: dict[str, Path]
    manifest: dict


_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def materialize_world_resources(
    pack: UserWorldPack,
    resource_root: Path | str,
) -> MaterializedWorldResources:
    """Write a world pack's file and SQLite resources into a scenario directory."""
    root = Path(resource_root)
    root.mkdir(parents=True, exist_ok=True)

    file_paths: dict[str, Path] = {}
    for file_resource in pack.resources.files:
        output_path = _safe_output_path(root, file_resource.path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(file_resource.content, encoding="utf-8")
        file_paths[file_resource.resource_id] = output_path

    database_paths: dict[str, Path] = {}
    for database_resource in pack.resources.databases:
        output_path = _safe_output_path(root, database_resource.path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            output_path.unlink()
        _write_sqlite_resource(output_path, database_resource)
        database_paths[database_resource.resource_id] = output_path

    manifest = {
        "world_id": pack.world_id,
        "schema_version": pack.schema_version,
        "files": {
            resource_id: _relative_posix(path, root)
            for resource_id, path in sorted(file_paths.items())
        },
        "databases": {
            resource_id: _relative_posix(path, root)
            for resource_id, path in sorted(database_paths.items())
        },
    }
    (root / "world_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return MaterializedWorldResources(
        resource_root=root,
        file_paths=file_paths,
        database_paths=database_paths,
        manifest=manifest,
    )


def _safe_output_path(root: Path, relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"resource path must stay under resource root: {relative_path!r}")
    resolved = (root / path).resolve()
    root_resolved = root.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise ValueError(f"resource path escapes resource root: {relative_path!r}")
    return resolved


def _write_sqlite_resource(path: Path, resource: DatabaseResourceSpec) -> None:
    with sqlite3.connect(path) as conn:
        for table_name, table in resource.tables.items():
            columns_sql = ", ".join(
                f"{_quote_identifier(column)} {type_decl}"
                for column, type_decl in table.columns.items()
            )
            conn.execute(
                f"CREATE TABLE {_quote_identifier(table_name)} ({columns_sql})"
            )
            column_names = list(table.columns)
            if not table.rows:
                continue
            placeholders = ", ".join("?" for _ in column_names)
            quoted_columns = ", ".join(_quote_identifier(column) for column in column_names)
            conn.executemany(
                (
                    f"INSERT INTO {_quote_identifier(table_name)} "
                    f"({quoted_columns}) VALUES ({placeholders})"
                ),
                [
                    tuple(row.get(column_name) for column_name in column_names)
                    for row in table.rows
                ],
            )


def _quote_identifier(identifier: str) -> str:
    if not _SQL_IDENTIFIER.fullmatch(identifier):
        raise ValueError(f"invalid SQLite identifier: {identifier!r}")
    return '"' + identifier.replace('"', '""') + '"'


def _relative_posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
