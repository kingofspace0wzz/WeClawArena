from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from clawsocialarena.worlds.models import UserWorldPack


class WorldPackLoadError(RuntimeError):
    """Raised when a world pack cannot be loaded or validated."""


def load_world_pack(path: Path | str) -> UserWorldPack:
    """Load a single world pack from a world directory or JSON file."""
    pack_path = Path(path)
    expected_world_id: str | None = None
    if pack_path.is_dir():
        expected_world_id = pack_path.name
        pack_path = pack_path / "world.json"

    if not pack_path.exists() or not pack_path.is_file():
        raise WorldPackLoadError(f"world pack file does not exist: {pack_path!s}")

    try:
        payload = json.loads(pack_path.read_text(encoding="utf-8"))
        pack = UserWorldPack.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise WorldPackLoadError(f"failed to load world pack {pack_path!s}: {exc}") from exc

    if expected_world_id is not None and pack.world_id != expected_world_id:
        raise WorldPackLoadError(
            f"world_id {pack.world_id!r} does not match directory "
            f"{expected_world_id!r}"
        )

    return pack


def load_world_packs(root: Path | str) -> list[UserWorldPack]:
    """Load all one-directory-per-world packs under ``root`` in sorted order."""
    root_path = Path(root)
    if not root_path.exists() or not root_path.is_dir():
        raise WorldPackLoadError(f"world pack root does not exist: {root_path!s}")

    packs: list[UserWorldPack] = []
    for world_dir in sorted(path for path in root_path.iterdir() if path.is_dir()):
        if (world_dir / "world.json").exists():
            packs.append(load_world_pack(world_dir))
    if not packs:
        raise WorldPackLoadError(f"world pack root contains no world.json files: {root_path!s}")
    return packs
