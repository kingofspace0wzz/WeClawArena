"""Gateway integration tests for resource MCP tools."""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from clawsocialarena.gateway.server import build_app
from clawsocialarena.gateway.session import Session
from clawsocialarena.protocols import PolicyDecision, PolicyVerdict
from clawsocialarena.types import ActionRecord, ActionType, AuditCondition


class BlockFsDeleteHook:
    hook_kind = "tool"

    def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
        if action.payload.get("tool_name") == "fs.delete":
            return PolicyDecision(
                verdict=PolicyVerdict.BLOCK,
                policy_id="block-delete",
                reason="delete requires explicit approval",
            )
        return PolicyDecision(verdict=PolicyVerdict.ALLOW)


def _manifest() -> dict:
    return {
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
                        "operations": ["fs.read", "fs.delete"],
                    }
                ],
            }
        }
    }


def _seed_file(root: Path) -> Path:
    path = root / "files/alice/private-notes.md"
    path.parent.mkdir(parents=True)
    path.write_text("Alice private note.\n")
    return path


@pytest.mark.asyncio
async def test_session_registers_resource_tools_for_gateway_dispatch(
    tmp_path: Path,
) -> None:
    resource_root = tmp_path / "resources"
    _seed_file(resource_root)
    session = Session.build(
        scenario_id="resource-tools",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "resource-tools.db",
        resource_root=resource_root,
        resource_manifest=_manifest(),
    )
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/mcp/fs.read",
            json={
                "agent_id": "alice",
                "arguments": {
                    "resource_id": "file-alice-notes",
                    "identity_id": "identity-alice-primary",
                    "scope_id": "scope-alice-files",
                },
            },
        )
        assert resp.status == 200
        body = await resp.json()

    assert body["blocked"] is False
    assert body["observation"]["content"] == "Alice private note.\n"
    assert session.action_log is not None
    assert [r.action_type for r in session.action_log.read_all()] == [
        ActionType.TOOL_CALL,
        ActionType.TOOL_OBSERVATION_RETURN,
    ]


@pytest.mark.asyncio
async def test_enforce_blocked_resource_tool_call_does_not_mutate(
    tmp_path: Path,
) -> None:
    resource_root = tmp_path / "resources"
    resource_file = _seed_file(resource_root)
    session = Session.build(
        scenario_id="resource-tools-block",
        condition=AuditCondition.ENFORCE,
        db_path=tmp_path / "resource-tools-block.db",
        hooks=[BlockFsDeleteHook()],
        resource_root=resource_root,
        resource_manifest=_manifest(),
    )
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/mcp/fs.delete",
            json={
                "agent_id": "alice",
                "arguments": {
                    "resource_id": "file-alice-notes",
                    "identity_id": "identity-alice-primary",
                    "scope_id": "scope-alice-files",
                },
            },
        )
        assert resp.status == 200
        body = await resp.json()

    assert body["blocked"] is True
    assert resource_file.exists()
    assert session.action_log is not None
    assert ActionType.TOOL_CALL not in [
        r.action_type for r in session.action_log.read_all()
    ]
