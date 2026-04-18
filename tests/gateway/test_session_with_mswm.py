"""Session wires MSWM into the online record pipeline (Phase C / Task C5).

MSWM is a cheap in-memory field on Session, always present regardless of
audit condition. Under BASELINE the Session short-circuits before reaching
``_record_action`` so MSWM stays empty; under PASSIVE or ENFORCE, every
recorded action that carries ``mentioned_items`` updates MSWM BEFORE any
policy hook fires. A blocked ENFORCE action reverts the MSWM update so the
state reflects "the message was suppressed".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.audit.mswm import MSWM
from clawsocialarena.gateway.session import Session
from clawsocialarena.protocols import PolicyDecision, PolicyVerdict
from clawsocialarena.types import ActionRecord, AuditCondition


def test_session_mswm_always_present(tmp_path: Path) -> None:
    baseline = Session.build(
        scenario_id="baseline-mswm",
        condition=AuditCondition.BASELINE,
        db_path=tmp_path / "ignored.db",
    )
    assert isinstance(baseline.mswm, MSWM)
    assert baseline.mswm.state == {}

    passive = Session.build(
        scenario_id="passive-mswm",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "passive.db",
    )
    assert isinstance(passive.mswm, MSWM)


@pytest.mark.asyncio
async def test_passive_outbound_updates_mswm(tmp_path: Path) -> None:
    session = Session.build(
        scenario_id="passive-outbound",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "passive.db",
    )
    outcome = await session._record_action(
        agent_id="alice",
        action_type=_OUTBOUND,
        payload={
            "recipient_id": "bob",
            "content": "hi",
            "mentioned_items": ["z"],
        },
        id_prefix="act",
        hook_target_content="hi",
    )
    assert outcome.blocked is False
    sender = session.mswm.get("alice", "bob")
    recipient = session.mswm.get("bob", "alice")
    assert len(sender.items_told_to_j) == 1
    assert len(recipient.items_learned_from_j) == 1


@pytest.mark.asyncio
async def test_enforce_block_reverts_mswm_update(tmp_path: Path) -> None:
    class BlockAll:
        hook_kind = "message"

        def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
            return PolicyDecision(verdict=PolicyVerdict.BLOCK, policy_id="bl")

    session = Session.build(
        scenario_id="enforce-block-mswm",
        condition=AuditCondition.ENFORCE,
        db_path=tmp_path / "enforce.db",
        hooks=[BlockAll()],
    )
    outcome = await session._record_action(
        agent_id="alice",
        action_type=_OUTBOUND,
        payload={
            "recipient_id": "bob",
            "content": "hi",
            "mentioned_items": ["z"],
        },
        id_prefix="act",
        hook_target_content="hi",
    )
    assert outcome.blocked is True
    # MSWM must be rolled back: no items_told_to_j, no items_learned_from_j.
    sender = session.mswm.get("alice", "bob")
    recipient = session.mswm.get("bob", "alice")
    assert sender.items_told_to_j == set()
    assert recipient.items_learned_from_j == set()


@pytest.mark.asyncio
async def test_hook_sees_mswm_context_with_current_action_already_applied(
    tmp_path: Path,
) -> None:
    """Hook evaluates AFTER MSWM has been updated for the current action."""

    seen_state: list[bool] = []

    class InspectMswm:
        hook_kind = "message"

        def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
            mswm = context.get("mswm")
            assert mswm is not None
            sender = mswm.get(action.agent_id, action.payload["recipient_id"])
            seen_state.append(bool(sender.items_told_to_j))
            return PolicyDecision(verdict=PolicyVerdict.ALLOW)

    session = Session.build(
        scenario_id="mswm-context",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "passive.db",
        hooks=[InspectMswm()],
    )
    await session._record_action(
        agent_id="alice",
        action_type=_OUTBOUND,
        payload={
            "recipient_id": "bob",
            "content": "hi",
            "mentioned_items": ["z"],
        },
        id_prefix="act",
        hook_target_content="hi",
    )
    # Hook observed the MSWM state AFTER the outbound update.
    assert seen_state == [True]


# Put the import at the bottom to keep the test file deliberate about what
# types it exercises directly.
from clawsocialarena.types import ActionType as _AT  # noqa: E402

_OUTBOUND = _AT.OUTBOUND_MESSAGE
