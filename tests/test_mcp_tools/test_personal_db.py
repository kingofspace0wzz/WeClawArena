"""Personal database resource MCP tool tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clawsocialarena.mcp_tools.personal_db import PersonalDatabaseTool
from clawsocialarena.scenario.models import ResourceManifest


def _manifest() -> ResourceManifest:
    return ResourceManifest.model_validate(
        {
            "resources": {
                "db-alice-health": {
                    "resource_id": "db-alice-health",
                    "type": "sqlite_db",
                    "owner_id": "owner-alice",
                    "sensitivity": "restricted",
                    "path": "db/alice.sqlite",
                    "table": "health_notes",
                    "row_filter": {"user_id": "alice"},
                    "allowed_operations": [
                        {
                            "identity_id": "identity-alice-primary",
                            "scope_id": "scope-alice-db",
                            "operations": ["db.query", "db.update", "db.delete"],
                        }
                    ],
                }
            }
        }
    )


def _seed_db(root: Path) -> None:
    db_path = root / "db/alice.sqlite"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE health_notes (user_id TEXT, note TEXT)")
        conn.executemany(
            "INSERT INTO health_notes (user_id, note) VALUES (?, ?)",
            [
                ("alice", "allergy: penicillin"),
                ("bob", "allergy: shellfish"),
            ],
        )


def test_personal_database_tool_queries_allowed_row_set(tmp_path: Path) -> None:
    _seed_db(tmp_path)
    tool = PersonalDatabaseTool(tmp_path, _manifest())

    result = tool.dispatch(
        "db.query",
        {
            "resource_id": "db-alice-health",
            "identity_id": "identity-alice-primary",
            "scope_id": "scope-alice-db",
            "where": {"user_id": "alice"},
        },
    )

    assert result == {
        "ok": True,
        "resource_id": "db-alice-health",
        "rows": [{"user_id": "alice", "note": "allergy: penicillin"}],
    }


def test_personal_database_tool_denies_out_of_scope_query(
    tmp_path: Path,
) -> None:
    _seed_db(tmp_path)
    tool = PersonalDatabaseTool(tmp_path, _manifest())

    result = tool.dispatch(
        "db.query",
        {
            "resource_id": "db-alice-health",
            "identity_id": "identity-alice-primary",
            "scope_id": "scope-alice-db",
            "where": {"user_id": "bob"},
        },
    )

    assert result["ok"] is False
    assert result["error"] == "row_filter_violation"


def test_personal_database_tool_updates_allowed_row_set(tmp_path: Path) -> None:
    _seed_db(tmp_path)
    tool = PersonalDatabaseTool(tmp_path, _manifest())

    result = tool.dispatch(
        "db.update",
        {
            "resource_id": "db-alice-health",
            "identity_id": "identity-alice-primary",
            "scope_id": "scope-alice-db",
            "where": {"user_id": "alice"},
            "values": {"note": "allergy: none"},
        },
    )

    assert result == {
        "ok": True,
        "resource_id": "db-alice-health",
        "rows_affected": 1,
    }
    with sqlite3.connect(tmp_path / "db/alice.sqlite") as conn:
        note = conn.execute(
            "SELECT note FROM health_notes WHERE user_id = 'alice'"
        ).fetchone()[0]
    assert note == "allergy: none"
