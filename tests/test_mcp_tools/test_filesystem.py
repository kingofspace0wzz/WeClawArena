"""Filesystem resource MCP tool tests."""

from __future__ import annotations

from pathlib import Path

from clawsocialarena.mcp_tools.filesystem import FilesystemResourceTool
from clawsocialarena.scenario.models import ResourceManifest


def _manifest() -> ResourceManifest:
    return ResourceManifest.model_validate(
        {
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
                            "operations": ["fs.read", "fs.write", "fs.delete"],
                        }
                    ],
                }
            }
        }
    )


def test_filesystem_tool_reads_allowed_resource(tmp_path: Path) -> None:
    resource_file = tmp_path / "files/alice/private-notes.md"
    resource_file.parent.mkdir(parents=True)
    resource_file.write_text("Alice private note.\n")
    tool = FilesystemResourceTool(tmp_path, _manifest())

    result = tool.dispatch(
        "fs.read",
        {
            "resource_id": "file-alice-notes",
            "identity_id": "identity-alice-primary",
            "scope_id": "scope-alice-files",
        },
    )

    assert result == {
        "ok": True,
        "resource_id": "file-alice-notes",
        "content": "Alice private note.\n",
    }


def test_filesystem_tool_denies_cross_identity_read(tmp_path: Path) -> None:
    resource_file = tmp_path / "files/alice/private-notes.md"
    resource_file.parent.mkdir(parents=True)
    resource_file.write_text("Alice private note.\n")
    tool = FilesystemResourceTool(tmp_path, _manifest())

    result = tool.dispatch(
        "fs.read",
        {"resource_id": "file-alice-notes", "identity_id": "identity-bob-primary"},
    )

    assert result["ok"] is False
    assert result["error"] == "forbidden"


def test_filesystem_tool_denied_delete_does_not_mutate(tmp_path: Path) -> None:
    resource_file = tmp_path / "files/alice/private-notes.md"
    resource_file.parent.mkdir(parents=True)
    resource_file.write_text("Alice private note.\n")
    tool = FilesystemResourceTool(tmp_path, _manifest())

    result = tool.dispatch(
        "fs.delete",
        {"resource_id": "file-alice-notes", "identity_id": "identity-bob-primary"},
    )

    assert result["ok"] is False
    assert resource_file.exists()
