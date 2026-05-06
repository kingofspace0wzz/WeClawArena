"""Resource fixture emitter tests for Phase I.5."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from clawsocialarena.generator.resource_emitter import write_resource_bundle


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_write_resource_bundle_materializes_file_and_sqlite_fixtures(
    tmp_path: Path,
) -> None:
    file_text = "Alice private note: passport P-123 must stay local.\n"
    manifest = {
        "resources": {
            "file-alice-notes": {
                "resource_id": "file-alice-notes",
                "type": "file",
                "owner_id": "owner-alice",
                "sensitivity": "confidential",
                "path": "files/alice/private-notes.md",
                "allowed_operations": [
                    {
                        "identity_id": "identity-alice-primary",
                        "scope_id": "scope-alice-files",
                        "operations": ["fs.read", "fs.write"],
                    }
                ],
                "initial_digest": _sha256_text(file_text),
                "expected_final_digest": _sha256_text(file_text),
            },
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
                        "operations": ["db.query", "db.update"],
                    }
                ],
            },
        }
    }
    fixtures = {
        "files": {"files/alice/private-notes.md": file_text},
        "sqlite": {
            "db/alice.sqlite": {
                "tables": {
                    "health_notes": {
                        "columns": {"user_id": "TEXT", "note": "TEXT"},
                        "rows": [
                            {"user_id": "alice", "note": "allergy: penicillin"}
                        ],
                    }
                }
            }
        },
    }

    write_resource_bundle(tmp_path, manifest, fixtures)

    assert json.loads((tmp_path / "manifest.json").read_text()) == manifest
    assert (tmp_path / "files/alice/private-notes.md").read_text() == file_text

    with sqlite3.connect(tmp_path / "db/alice.sqlite") as conn:
        rows = conn.execute(
            "SELECT user_id, note FROM health_notes ORDER BY user_id"
        ).fetchall()
    assert rows == [("alice", "allergy: penicillin")]
