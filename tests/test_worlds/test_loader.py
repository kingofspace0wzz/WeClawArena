import json

import pytest

from clawsocialarena.worlds.loader import WorldPackLoadError, load_world_pack, load_world_packs
from clawsocialarena.worlds.models import UserWorldPack


def _world_payload(world_id: str = "world-travel-clinic-001") -> dict:
    return {
        "world_id": world_id,
        "schema_version": "world-pack-v1",
        "users": [
            {
                "user_id": "user-alex",
                "profile_source": {
                    "dataset": "AgentSocialBench",
                    "dataset_version": "asb-v1",
                    "profile_ref": "asb://profiles/profile_alex",
                    "profile_hash": "sha256:profile",
                    "privacy_boundary_refs": ["asb://profiles/profile_alex#health"],
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
            ]
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


def test_load_world_pack_from_directory(tmp_path) -> None:
    world_dir = tmp_path / "world-travel-clinic-001"
    world_dir.mkdir()
    (world_dir / "world.json").write_text(
        json.dumps(_world_payload()),
        encoding="utf-8",
    )

    pack = load_world_pack(world_dir)

    assert isinstance(pack, UserWorldPack)
    assert pack.world_id == "world-travel-clinic-001"
    assert pack.resources.files[0].path == "home/notes/travel.md"


def test_load_world_pack_rejects_directory_id_mismatch(tmp_path) -> None:
    world_dir = tmp_path / "world-travel-clinic-001"
    world_dir.mkdir()
    (world_dir / "world.json").write_text(
        json.dumps(_world_payload(world_id="world-other")),
        encoding="utf-8",
    )

    with pytest.raises(WorldPackLoadError, match="does not match directory"):
        load_world_pack(world_dir)


def test_load_world_packs_loads_sorted_directories(tmp_path) -> None:
    for world_id in ("world-b", "world-a"):
        world_dir = tmp_path / world_id
        world_dir.mkdir()
        (world_dir / "world.json").write_text(
            json.dumps(_world_payload(world_id=world_id)),
            encoding="utf-8",
        )

    packs = load_world_packs(tmp_path)

    assert [pack.world_id for pack in packs] == ["world-a", "world-b"]
