"""Session wires MSWM into the online record pipeline (Phase C / Task C5).

MSWM is a cheap in-memory field on Session, always present regardless of
audit condition. Under BASELINE the Session short-circuits before reaching
``_record_action`` so MSWM stays empty; under PASSIVE or ENFORCE, every
recorded action that carries ``mentioned_items`` updates a tentative MSWM
view BEFORE any policy hook fires. A blocked ENFORCE action discards that
tentative update so committed state reflects "the message was suppressed".
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
async def test_enforce_block_discards_candidate_mswm_update(tmp_path: Path) -> None:
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
    # Committed MSWM excludes the blocked candidate update.
    sender = session.mswm.get("alice", "bob")
    recipient = session.mswm.get("bob", "alice")
    assert sender.items_told_to_j == set()
    assert recipient.items_learned_from_j == set()


@pytest.mark.asyncio
async def test_hook_sees_mswm_context_with_candidate_action_in_tentative_view(
    tmp_path: Path,
) -> None:
    """Hook evaluates against the candidate action in the tentative MSWM."""

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
    # Hook observed the candidate action's tentative MSWM update.
    assert seen_state == [True]


@pytest.mark.asyncio
async def test_hook_context_exposes_committed_and_tentative_mswm(
    tmp_path: Path,
) -> None:
    seen: list[tuple[set[str], set[str], bool]] = []

    class InspectContext:
        hook_kind = "message"

        def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
            committed = context["mswm_committed"]
            tentative = context["mswm_tentative"]
            seen.append(
                (
                    committed.known_items("bob"),
                    tentative.known_items("bob"),
                    context["mswm"] is tentative,
                )
            )
            return PolicyDecision(verdict=PolicyVerdict.ALLOW)

    session = Session.build(
        scenario_id="mswm-context-views",
        condition=AuditCondition.PASSIVE,
        db_path=tmp_path / "passive.db",
        hooks=[InspectContext()],
    )

    await session.record_outbound(
        sender_id="alice",
        recipient_id="bob",
        content="hi",
        mentioned_items=["z"],
    )

    assert seen == [(set(), {"z"}, True)]
    assert session.mswm.known_items("bob") == {"z"}


@pytest.mark.asyncio
async def test_block_discards_tentative_mswm_without_revert_call(
    tmp_path: Path,
) -> None:
    class BlockAll:
        hook_kind = "message"

        def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
            return PolicyDecision(verdict=PolicyVerdict.BLOCK, policy_id="bl")

    session = Session.build(
        scenario_id="block-no-revert",
        condition=AuditCondition.ENFORCE,
        db_path=tmp_path / "enforce.db",
        hooks=[BlockAll()],
    )

    def fail_revert(action: ActionRecord) -> None:
        raise AssertionError("revert_action should not be used by transaction flow")

    session.mswm.revert_action = fail_revert  # type: ignore[method-assign]

    outcome = await session.record_outbound(
        sender_id="alice",
        recipient_id="bob",
        content="hi",
        mentioned_items=["z"],
    )

    assert outcome.blocked is True
    assert session.mswm.known_items("bob") == set()


@pytest.mark.asyncio
async def test_committed_context_view_is_isolated_from_hook_mutation(
    tmp_path: Path,
) -> None:
    class InspectCommittedThenBlock:
        hook_kind = "message"

        def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
            context["mswm_committed"].get(
                action.agent_id,
                action.payload["recipient_id"],
            )
            return PolicyDecision(verdict=PolicyVerdict.BLOCK, policy_id="bl")

    session = Session.build(
        scenario_id="committed-context-isolated",
        condition=AuditCondition.ENFORCE,
        db_path=tmp_path / "enforce.db",
        hooks=[InspectCommittedThenBlock()],
    )

    outcome = await session.record_outbound(
        sender_id="alice",
        recipient_id="bob",
        content="hi",
        mentioned_items=["z"],
    )

    assert outcome.blocked is True
    assert session.mswm.state == {}


@pytest.mark.asyncio
async def test_committed_context_mutation_does_not_leak_through_rewrite(
    tmp_path: Path,
) -> None:
    class MutateCommittedAndRewrite:
        hook_kind = "message"

        def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
            context["mswm_committed"].get("ghost", "peer")
            return PolicyDecision(
                verdict=PolicyVerdict.REWRITE,
                rewritten_content=action.payload["content"],
                rewritten_mentioned_items=["safe_item"],
                policy_id="rewrite-after-committed-inspect",
            )

    session = Session.build(
        scenario_id="committed-context-rewrite-isolated",
        condition=AuditCondition.ENFORCE,
        db_path=tmp_path / "enforce.db",
        hooks=[MutateCommittedAndRewrite()],
    )

    outcome = await session.record_outbound(
        sender_id="alice",
        recipient_id="bob",
        content="hi",
        mentioned_items=["safe_item", "forbidden_item"],
    )

    assert outcome.blocked is False
    assert "ghost" not in session.mswm.state
    assert session.mswm.known_items("bob") == {"safe_item"}


@pytest.mark.asyncio
async def test_rewrite_rebuilds_tentative_before_later_hooks(
    tmp_path: Path,
) -> None:
    observed: list[set[str]] = []

    class RewriteMentioned:
        hook_kind = "message"

        def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
            return PolicyDecision(
                verdict=PolicyVerdict.REWRITE,
                rewritten_content=action.payload["content"],
                rewritten_mentioned_items=["safe_item"],
                policy_id="rewrite-mentioned",
            )

    class InspectAfterRewrite:
        hook_kind = "message"

        def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
            observed.append(context["mswm_tentative"].known_items("bob"))
            return PolicyDecision(verdict=PolicyVerdict.ALLOW)

    session = Session.build(
        scenario_id="rewrite-rebuilds-tentative",
        condition=AuditCondition.ENFORCE,
        db_path=tmp_path / "enforce.db",
        hooks=[RewriteMentioned(), InspectAfterRewrite()],
    )

    outcome = await session.record_outbound(
        sender_id="alice",
        recipient_id="bob",
        content="hi",
        mentioned_items=["safe_item", "forbidden_item"],
    )

    assert outcome.blocked is False
    assert observed == [{"safe_item"}]
    assert session.mswm.known_items("bob") == {"safe_item"}


# Put the import at the bottom to keep the test file deliberate about what
# types it exercises directly.
from clawsocialarena.types import ActionType as _AT  # noqa: E402

_OUTBOUND = _AT.OUTBOUND_MESSAGE
