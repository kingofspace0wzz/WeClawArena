"""Gateway tests for governance logging and enforcement."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aiohttp.test_utils import TestClient, TestServer

from clawsocialarena.gateway.server import build_app
from clawsocialarena.gateway.session import Session
from clawsocialarena.types import ActionType, AuditCondition


def _manifest() -> dict[str, Any]:
    return {
        "owners": {
            "owner-alice": {
                "owner_id": "owner-alice",
                "user_id": "user-a",
                "display_name": "Alice",
            }
        },
        "identities": {
            "identity-alice-delegate": {
                "identity_id": "identity-alice-delegate",
                "owner_id": "owner-alice",
                "agent_id": "alice",
                "label": "Alice delegate",
            }
        },
        "authorization_scopes": {
            "scope-calendar-write": {
                "scope_id": "scope-calendar-write",
                "owner_id": "owner-alice",
                "identity_id": "identity-alice-delegate",
                "resource_ids": ["calendar://alice/work"],
                "allowed_actions": [
                    "outbound_message",
                    "memory_write",
                    "llm_call",
                    "tool_observation_return",
                    "calendar.write",
                ],
                "constraints": {},
            }
        },
        "approval_mandates": {
            "mandate-owner-approval": {
                "mandate_id": "mandate-owner-approval",
                "owner_id": "owner-alice",
                "scope_id": "scope-calendar-write",
                "approver_ids": ["owner-alice"],
                "approval_mode": "owner_explicit",
            }
        },
        "escalation_rules": {
            "rule-approved": {
                "rule_id": "rule-approved",
                "from_state": "pending_owner_review",
                "to_state": "approved",
                "trigger": "owner_approved",
                "required_actor_id": "owner-alice",
            }
        },
    }


def _governance(**overrides: str) -> dict[str, str]:
    data = {
        "owner_id": "owner-alice",
        "active_identity_id": "identity-alice-delegate",
        "authorization_scope_id": "scope-calendar-write",
        "approval_mandate_id": "mandate-owner-approval",
        "escalation_state": "approved",
    }
    data.update(overrides)
    return data


def _session(
    tmp_path: Path,
    condition: AuditCondition,
    suffix: str,
) -> Session:
    return Session.build(
        scenario_id=f"governance-{suffix}",
        condition=condition,
        db_path=tmp_path / f"{suffix}.db",
        governance_manifest=_manifest(),
    )


@pytest.mark.asyncio
async def test_passive_logs_governance_verdict_but_delivers_message(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, AuditCondition.PASSIVE, "passive")
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        send = await client.post(
            "/send",
            json={
                "sender_id": "alice",
                "recipient_id": "bob",
                "content": "hello",
                "governance": _governance(escalation_state="denied"),
            },
        )
        assert send.status == 200
        assert await send.json() != {"action_id": None, "blocked": True}

        recv = await client.post("/recv", json={"recipient_id": "bob"})
        assert recv.status == 200
        assert await recv.json() == {"sender_id": "alice", "content": "hello"}

    rows = session.action_log.read_all()  # type: ignore[union-attr]
    out = next(r for r in rows if r.action_type == ActionType.OUTBOUND_MESSAGE)
    pol = next(r for r in rows if r.action_type == ActionType.POLICY_DECISION)
    assert out.governance is not None
    assert pol.payload["verdict"] == "block"
    assert pol.payload["audit_condition"] == "passive"
    assert pol.payload["enforced"] is False
    assert pol.payload["enforcement_effect"] == "would_block_audit_only"
    assert pol.payload["governance_verdict"]["decision"] == "block"
    assert "escalation_denied" in pol.payload["governance_verdict"]["violations"]


@pytest.mark.asyncio
async def test_enforce_blocks_governance_violation_without_queue_or_mswm_update(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, AuditCondition.ENFORCE, "enforce")
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/send",
            json={
                "sender_id": "alice",
                "recipient_id": "bob",
                "content": "hello",
                "mentioned_items": ["private_fact"],
                "governance": _governance(escalation_state="pending_owner_review"),
            },
        )
        assert resp.status == 200
        assert await resp.json() == {"action_id": None, "blocked": True}

        recv = await client.post("/recv", json={"recipient_id": "bob"})
        assert recv.status == 204

    rows = session.action_log.read_all()  # type: ignore[union-attr]
    assert [r.action_type for r in rows] == [ActionType.POLICY_DECISION]
    assert rows[0].payload["audit_condition"] == "enforce"
    assert rows[0].payload["enforced"] is True
    assert rows[0].payload["enforcement_effect"] == "blocked"
    assert rows[0].payload["governance_verdict"]["requires_owner_approval"] is True
    assert "owner_approval_missing" in rows[0].payload["governance_verdict"]["violations"]
    assert session.mswm.known_items("bob") == set()


@pytest.mark.asyncio
async def test_baseline_forwards_even_with_governance_manifest_and_bad_governance(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, AuditCondition.BASELINE, "baseline")
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/send",
            json={
                "sender_id": "alice",
                "recipient_id": "bob",
                "content": "hello",
                "governance": _governance(escalation_state="denied"),
            },
        )
        assert resp.status == 200
        assert await resp.json() == {"action_id": None, "blocked": False}

        recv = await client.post("/recv", json={"recipient_id": "bob"})
        assert recv.status == 200
        assert await recv.json() == {"sender_id": "alice", "content": "hello"}

    assert session.action_log is None
    assert session.hooks == []


@pytest.mark.asyncio
async def test_governance_hook_runs_for_llm_call_and_tool_observation(
    tmp_path: Path,
) -> None:
    session = _session(tmp_path, AuditCondition.PASSIVE, "sidechannels")
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        llm = await client.post(
            "/llm_call",
            json={
                "agent_id": "alice",
                "input_tokens": 1,
                "output_tokens": 2,
                "latency_ms": 3,
                "model": "test-model",
                "governance": _governance(),
            },
        )
        assert llm.status == 200

        obs = await client.post(
            "/tool_observation_return",
            json={
                "agent_id": "alice",
                "tool_call_action_id": "tc-1",
                "tool_name": "calendar",
                "observation": "ok",
                "governance": _governance(),
            },
        )
        assert obs.status == 200

    rows = session.action_log.read_all()  # type: ignore[union-attr]
    observed = [r for r in rows if r.action_type != ActionType.POLICY_DECISION]
    policies = [r for r in rows if r.action_type == ActionType.POLICY_DECISION]
    assert [r.action_type for r in observed] == [
        ActionType.LLM_CALL,
        ActionType.TOOL_OBSERVATION_RETURN,
    ]
    assert len(policies) == 2
    assert all(p.payload["governance_verdict"]["decision"] == "allow" for p in policies)
    assert all(r.governance is not None for r in observed)


@pytest.mark.asyncio
async def test_enforce_blocks_out_of_scope_mcp_before_dispatch(tmp_path: Path) -> None:
    session = _session(tmp_path, AuditCondition.ENFORCE, "mcp")

    def fail_if_called(**_: Any) -> dict[str, bool]:
        raise AssertionError("MCP tool should not run")

    session.mcp_host.register("calendar", fail_if_called)
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/mcp/calendar",
            json={
                "agent_id": "alice",
                "arguments": {
                    "action": "calendar.write",
                    "resource_id": "calendar://alice/private",
                },
                "governance": _governance(),
            },
        )
        assert resp.status == 200
        assert await resp.json() == {
            "tool_call_action_id": None,
            "tool_observation_action_id": None,
            "observation": None,
            "blocked": True,
        }

    rows = session.action_log.read_all()  # type: ignore[union-attr]
    assert [r.action_type for r in rows] == [ActionType.POLICY_DECISION]
    verdict = rows[0].payload["governance_verdict"]
    assert verdict["decision"] == "block"
    assert "resource_out_of_scope" in verdict["violations"]


@pytest.mark.asyncio
async def test_enforce_blocks_mcp_observation_after_allowed_tool_call(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    manifest["authorization_scopes"]["scope-calendar-write"]["allowed_actions"] = [
        "calendar.write"
    ]
    session = Session.build(
        scenario_id="governance-mcp-observation",
        condition=AuditCondition.ENFORCE,
        db_path=tmp_path / "mcp-observation.db",
        governance_manifest=manifest,
    )
    dispatch_count = 0

    def calendar(_: dict[str, Any]) -> dict[str, str]:
        nonlocal dispatch_count
        dispatch_count += 1
        return {"result": "ok"}

    session.mcp_host.register("calendar", calendar)
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/mcp/calendar",
            json={
                "agent_id": "alice",
                "arguments": {
                    "action": "calendar.write",
                    "resource_id": "calendar://alice/work",
                },
                "governance": _governance(),
            },
        )
        assert resp.status == 200
        body = await resp.json()

    assert body == {
        "tool_call_action_id": body["tool_call_action_id"],
        "tool_observation_action_id": None,
        "observation": None,
        "blocked": True,
    }
    assert body["tool_call_action_id"] is not None
    assert dispatch_count == 1

    rows = session.action_log.read_all()  # type: ignore[union-attr]
    assert [r.action_type for r in rows] == [
        ActionType.POLICY_DECISION,
        ActionType.TOOL_CALL,
        ActionType.POLICY_DECISION,
    ]
    assert rows[-1].payload["governance_verdict"]["decision"] == "block"
    assert "action_out_of_scope" in rows[-1].payload["governance_verdict"]["violations"]


@pytest.mark.asyncio
async def test_routes_reject_malformed_governance(tmp_path: Path) -> None:
    session = _session(tmp_path, AuditCondition.PASSIVE, "bad-governance")
    app = build_app(session)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/memory_write",
            json={
                "agent_id": "alice",
                "content": "note",
                "governance": {"owner_id": "owner-alice"},
            },
        )
        assert resp.status == 400
        body = await resp.json()

    assert body["field"] == "governance"
