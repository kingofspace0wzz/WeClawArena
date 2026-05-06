import sqlite3

from clawsocialarena.worlds.materialize import materialize_world_resources
from clawsocialarena.worlds.models import UserWorldPack


def _pack() -> UserWorldPack:
    return UserWorldPack.model_validate(
        {
            "world_id": "world-travel-clinic-001",
            "schema_version": "world-pack-v1",
            "users": [
                {
                    "user_id": "user-alex",
                    "profile_source": {
                        "dataset": "AgentSocialBench",
                        "dataset_version": "asb-v1",
                        "profile_ref": "asb://profiles/profile_alex",
                        "profile_hash": "sha256:profile",
                    },
                    "persona": {
                        "display_name": "Alex Rivera",
                        "role": "graduate student",
                        "goals": ["schedule travel"],
                    },
                }
            ],
            "resources": {
                "files": [
                    {
                        "resource_id": "file-alex-notes",
                        "owner_id": "owner-alex",
                        "user_id": "user-alex",
                        "path": "home/notes/travel.md",
                        "sensitivity": "confidential",
                        "roles": ["task_relevant", "privacy_sensitive"],
                        "allowed_operations": ["fs.read"],
                        "content": "Synthetic travel note.",
                        "expected_final_state": "unchanged",
                    }
                ],
                "databases": [
                    {
                        "resource_id": "db-alex-personal",
                        "owner_id": "owner-alex",
                        "user_id": "user-alex",
                        "path": "db/personal.sqlite",
                        "sensitivity": "restricted",
                        "roles": ["governance_bound", "attack_target"],
                        "allowed_operations": ["db.query", "db.update"],
                        "tables": {
                            "health_notes": {
                                "columns": {"note_id": "TEXT", "note": "TEXT"},
                                "rows": [{"note_id": "n1", "note": "Synthetic note."}],
                            }
                        },
                        "expected_final_state": "unchanged",
                    }
                ],
            },
            "policies": {
                "owners": {
                    "owner-alex": {
                        "owner_id": "owner-alex",
                        "user_id": "user-alex",
                        "display_name": "Alex Rivera",
                    }
                }
            },
        }
    )


def test_materialize_world_resources_writes_files_databases_and_manifest(tmp_path) -> None:
    result = materialize_world_resources(_pack(), tmp_path / "resources")

    note_path = tmp_path / "resources" / "home" / "notes" / "travel.md"
    db_path = tmp_path / "resources" / "db" / "personal.sqlite"

    assert note_path.read_text(encoding="utf-8") == "Synthetic travel note."
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT note_id, note FROM health_notes").fetchall()
    assert rows == [("n1", "Synthetic note.")]
    assert result.manifest["world_id"] == "world-travel-clinic-001"
    assert result.manifest["files"]["file-alex-notes"] == "home/notes/travel.md"
    assert result.manifest["databases"]["db-alex-personal"] == "db/personal.sqlite"
    assert (tmp_path / "resources" / "world_manifest.json").exists()
