"""Gateway-hosted filesystem resource MCP tools."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from clawsocialarena.scenario.models import ResourceEntry, ResourceManifest


class FilesystemResourceTool:
    """Dispatch ``fs.*`` operations against declared resource files."""

    def __init__(
        self,
        resource_root: Path | str,
        resource_manifest: ResourceManifest | dict[str, Any],
    ) -> None:
        self.resource_root = Path(resource_root).resolve()
        self.resource_manifest = ResourceManifest.model_validate(resource_manifest)

    def dispatch(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        resource_id = arguments.get("resource_id")
        if not isinstance(resource_id, str) or resource_id == "":
            return {"ok": False, "error": "missing_resource_id"}
        entry = self.resource_manifest.resources.get(resource_id)
        if entry is None:
            return {"ok": False, "error": "unknown_resource", "resource_id": resource_id}
        if not _is_authorized(entry, operation, arguments):
            return {"ok": False, "error": "forbidden", "resource_id": resource_id}
        try:
            path = self._entry_path(entry)
        except ValueError as exc:
            return {
                "ok": False,
                "error": "invalid_resource_path",
                "resource_id": resource_id,
                "details": str(exc),
            }

        if operation == "fs.read":
            return self._read(resource_id, path)
        if operation == "fs.write":
            return self._write(resource_id, path, arguments)
        if operation == "fs.delete":
            return self._delete(resource_id, path)
        if operation == "fs.list":
            return self._list(resource_id, path)
        return {"ok": False, "error": "unsupported_operation", "operation": operation}

    def _entry_path(self, entry: ResourceEntry) -> Path:
        if entry.path is None:
            raise ValueError("resource has no path")
        rel = Path(entry.path)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"path escapes resources/: {entry.path!r}")
        path = (self.resource_root / rel).resolve()
        if not path.is_relative_to(self.resource_root):
            raise ValueError(f"path escapes resources/: {entry.path!r}")
        return path

    @staticmethod
    def _read(resource_id: str, path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {"ok": False, "error": "not_found", "resource_id": resource_id}
        return {
            "ok": True,
            "resource_id": resource_id,
            "content": path.read_text(),
        }

    @staticmethod
    def _write(
        resource_id: str,
        path: Path,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        content = arguments.get("content")
        if not isinstance(content, str):
            return {
                "ok": False,
                "error": "invalid_content",
                "resource_id": resource_id,
            }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return {
            "ok": True,
            "resource_id": resource_id,
            "bytes_written": len(content.encode("utf-8")),
        }

    @staticmethod
    def _delete(resource_id: str, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"ok": False, "error": "not_found", "resource_id": resource_id}
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return {"ok": True, "resource_id": resource_id, "deleted": True}

    @staticmethod
    def _list(resource_id: str, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"ok": False, "error": "not_found", "resource_id": resource_id}
        if path.is_file():
            entries = [path.name]
        else:
            entries = sorted(child.name for child in path.iterdir())
        return {"ok": True, "resource_id": resource_id, "entries": entries}


def _is_authorized(
    entry: ResourceEntry,
    operation: str,
    arguments: dict[str, Any],
) -> bool:
    identity_id = arguments.get("identity_id")
    scope_id = arguments.get("scope_id")
    for rule in entry.allowed_operations:
        if operation not in rule.operations:
            continue
        if rule.identity_id is not None and rule.identity_id != identity_id:
            continue
        if rule.scope_id is not None and rule.scope_id != scope_id:
            continue
        return True
    return False
