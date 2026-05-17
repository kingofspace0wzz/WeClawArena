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
    hub_aggregator archetypes).

    A shared resource may carry a single SQLite table (legacy single-table
    form: pass ``schema`` and ``rows``), or multiple SQLite tables under
    one resource id (multi-table form: pass ``tables``). When ``tables``
    is set, it supersedes ``schema`` / ``rows`` and the materializer
    iterates the nested ``WorkspaceTableSeed`` entries.

    The hub_aggregator archetype uses the multi-table form to keep
    ``orders`` and ``order_line_items`` under a single shared resource id
    so the ``aggregated_order_includes_all_spokes`` predicate can join
    across them within the same sqlite file.
    """

    shared_resource_id: str
    schema: str = ""
    rows: tuple[dict[str, Any], ...] = ()
    tables: tuple[WorkspaceTableSeed, ...] | None = None
