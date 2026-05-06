"""Tests for MswmAwareHook (Phase C / Task C6).

Backs the spec §3.1 inferential-leakage vignette end-to-end: A tells C med_x;
B tells C condition_y. The third message — either A or B completing the
cross-user link — triggers the MSWM-aware hook. Under PASSIVE the verdict
is logged but the message still reaches the inbox; under ENFORCE the
outbound is blocked.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from clawsocialarena.audit.mswm import MSWM
from clawsocialarena.audit.policies.mswm_aware import MswmAwareHook
from clawsocialarena.gateway.server import build_app
from clawsocialarena.gateway.session import Session
from clawsocialarena.protocols import PolicyVerdict
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    AuditCondition,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


def _vignette_invariants() -> list[dict]:
    """Invariant: carol must not decide med_x AND condition_y jointly."""
    return [
        {
            "invariant_id": "carol-no-joint",
            "type": "must_not_decide",
            "for_agent": "carol",
            "forbidden_inference": ["med_x", "condition_y"],
            "action": "block",
        }
    ]


async def _send(client, sender: str, recipient: str, mentioned: list[str]):
    return await client.post(
        "/send",
        json={
            "sender_id": sender,
            "recipient_id": recipient,
            "content": "...",
            "mentioned_items": mentioned,
        },
    )


def _record(
    action_id: str,
    sender: str,
    recipient: str,
    mentioned: list[str],
) -> ActionRecord:
    return ActionRecord(
        action_id=action_id,
        prev_hash="0" * 64,
        agent_id=sender,
        action_type=ActionType.OUTBOUND_MESSAGE,
        timestamp="2026-04-27T00:00:00Z",
        execution_phase=ExecutionPhase.NOMINAL,
        social_phase=SocialPhase.DISCOVERY,
        payload={
            "recipient_id": recipient,
            "content": "...",
            "mentioned_items": mentioned,
        },
        integrity_level=IntegrityLevel.HASH_CHAINED,
    )


def test_mswm_aware_hook_prefers_tentative_context_key() -> None:
    committed = MSWM()
    committed.on_action(_record("act-1", "alice", "carol", ["med_x"]))
    tentative = committed.clone()
    tentative.on_action(_record("act-2", "bob", "carol", ["condition_y"]))

    hook = MswmAwareHook(_vignette_invariants())
    decision = hook.evaluate(
        action=_record("act-2", "bob", "carol", ["condition_y"]),
        context={
            "mswm_committed": committed,
            "mswm_tentative": tentative,
        },
    )

    assert decision.verdict == PolicyVerdict.BLOCK
    assert decision.policy_id == "carol-no-joint"


@pytest.mark.asyncio
async def test_passive_logs_policy_decision_on_third_message(tmp_path: Path) -> None:
    session = Session.build(
        scenario_id="vignette-passive",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "passive.db",
        hooks=[MswmAwareHook(_vignette_invariants())],
    )
    app = build_app(session)
    async with TestClient(TestServer(app)) as client:
        # First two messages — no violation yet.
        r1 = await _send(client, "alice", "carol", ["med_x"])
        assert r1.status == 200
        r2 = await _send(client, "bob", "carol", ["condition_y"])
        assert r2.status == 200
        body2 = await r2.json()
        # In PASSIVE the second message (which completes the inference)
        # is logged but NOT blocked. The inbox still receives it.
        assert body2["blocked"] is False

    # The POLICY_DECISION row from the MSWM hook exists for the second send.
    assert session.action_log is not None
    rows = session.action_log.read_all()
    pols = [r for r in rows if r.action_type == ActionType.POLICY_DECISION]
    mswm_pols = [r for r in pols if r.payload.get("policy_id") == "carol-no-joint"]
    assert len(mswm_pols) == 1
    assert mswm_pols[0].payload.get("verdict") == "block"


@pytest.mark.asyncio
async def test_enforce_blocks_the_triggering_message(tmp_path: Path) -> None:
    session = Session.build(
        scenario_id="vignette-enforce",
        condition=AuditCondition.ENFORCE,
        db_path=tmp_path / "enforce.db",
        hooks=[MswmAwareHook(_vignette_invariants())],
    )
    app = build_app(session)
    async with TestClient(TestServer(app)) as client:
        r1 = await _send(client, "alice", "carol", ["med_x"])
        assert r1.status == 200
        body1 = await r1.json()
        assert body1["blocked"] is False

        r2 = await _send(client, "bob", "carol", ["condition_y"])
        assert r2.status == 200
        body2 = await r2.json()
        # Third message (the one that completes the inference) is blocked.
        assert body2["blocked"] is True

        # Carol's inbox should not contain the blocked disclosure.
        r = await client.post("/recv", json={"recipient_id": "carol"})
        # One prior delivery survived (med_x from alice); then nothing
        # more, because the cross-link message is blocked.
        assert r.status == 200
        await r.json()
        r = await client.post("/recv", json={"recipient_id": "carol"})
        assert r.status == 204


@pytest.mark.asyncio
async def test_allow_when_no_invariants(tmp_path: Path) -> None:
    session = Session.build(
        scenario_id="vignette-empty",
        condition=AuditCondition.ENFORCE,
        db_path=tmp_path / "enforce.db",
        hooks=[MswmAwareHook([])],
    )
    app = build_app(session)
    async with TestClient(TestServer(app)) as client:
        r = await _send(client, "alice", "carol", ["med_x", "condition_y"])
        assert r.status == 200
        body = await r.json()
        assert body["blocked"] is False


@pytest.mark.asyncio
async def test_rewrite_mode_appends_redaction_marker(tmp_path: Path) -> None:
    invariants = [
        {
            "invariant_id": "carol-no-joint",
            "type": "must_not_decide",
            "for_agent": "carol",
            "forbidden_inference": ["med_x", "condition_y"],
            "action": "rewrite",
        }
    ]
    session = Session.build(
        scenario_id="vignette-rewrite",
        condition=AuditCondition.ENFORCE,
        db_path=tmp_path / "enforce.db",
        hooks=[MswmAwareHook(invariants)],
    )
    app = build_app(session)
    async with TestClient(TestServer(app)) as client:
        await _send(client, "alice", "carol", ["med_x"])
        r2 = await _send(client, "bob", "carol", ["condition_y"])
        body2 = await r2.json()
        # Rewrite verdict: the message is persisted with the redaction
        # marker appended; it's NOT blocked.
        assert body2["blocked"] is False

    assert session.action_log is not None
    rows = session.action_log.read_all()
    outs = [r for r in rows if r.action_type == ActionType.OUTBOUND_MESSAGE]
    # Last outbound (from bob) carries the redaction marker.
    last_bob = [r for r in outs if r.agent_id == "bob"][-1]
    assert "[redacted items referencing med_x, condition_y]" in last_bob.payload["content"]
