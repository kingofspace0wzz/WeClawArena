"""Shared dataclasses for tau2_retail per-archetype seed files.

Each archetype's seed file imports these primitives and builds a tuple
of archetype-specific TaskSeed entries. The shapes mirror the
marble_bargaining seed pattern (WorkspaceFileSeed, WorkspaceTableSeed,
OwnerWorkspaceSeed) so the materializer's resource-emitter code can
stay archetype-agnostic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkspaceFileSeed:
    """One personal markdown file in an owner's workspace.

    ``protected=True`` marks the file as confidential at the
    resource_manifest level; cross-owner reads of protected files are
    privacy-scorer events. ``protected=False`` files are still
    owner-private at the filesystem level, but their content is
    treated as untrusted input (the indirect-prompt-injection delivery
    surface).
    """

    path: str
    content: str
    protected: bool = False


@dataclass(frozen=True)
class WorkspaceTableSeed:
    """One SQLite table in an owner's personal.sqlite database.

    ``rows`` is a tuple of dicts keyed by column name. The materializer
    serializes them to INSERT statements using the column order in
    ``schema``.
    """

    name: str
    schema: str
    rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class OwnerWorkspaceSeed:
    """All owned resources for one owner (files + tables)."""

    owner_id: str
    role_label: str
    files: tuple[WorkspaceFileSeed, ...]
    tables: tuple[WorkspaceTableSeed, ...]

    def as_loader_dict(self) -> dict[str, Any]:
        return {
            "owner_id": self.owner_id,
            "role_label": self.role_label,
            "files": tuple(
                {
                    "path": file.path,
                    "content": file.content,
                    "protected": file.protected,
                }
                for file in self.files
            ),
            "tables": tuple(
                {
                    "name": table.name,
                    "schema": table.schema,
                    "rows": tuple(dict(row) for row in table.rows),
                }
                for table in self.tables
            ),
        }


@dataclass(frozen=True)
class SharedResourceSeed:
    """A cross-owner-readable resource (only for shared_account and
    hub_aggregator archetypes)."""

    shared_resource_id: str
    schema: str
    rows: tuple[dict[str, Any], ...]
