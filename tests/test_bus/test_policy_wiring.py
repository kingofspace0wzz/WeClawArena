from pathlib import Path

import pytest

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.shadow_log import ShadowLog
from clawsocialarena.bus.audited import AuditedMessageBus
from clawsocialarena.bus.in_process import InProcessMessageBus
from clawsocialarena.protocols import PolicyDecision, PolicyVerdict
from clawsocialarena.types import ActionRecord, ActionType, AuditCondition


class StubRewriteHook:
    def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
        content = action.payload.get("content", "")
        if "secret" in content.lower():
            return PolicyDecision(
                verdict=PolicyVerdict.REWRITE,
                rewritten_content=content.replace("secret", "[redacted]"),
                reason="contains 'secret'",
                policy_id="no-secrets",
            )
        return PolicyDecision(verdict=PolicyVerdict.ALLOW)


class StubBlockHook:
    def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
        content = action.payload.get("content", "")
        if "BLOCKME" in content:
            return PolicyDecision(
                verdict=PolicyVerdict.BLOCK, policy_id="block-marker"
            )
        return PolicyDecision(verdict=PolicyVerdict.ALLOW)


def _make_bus(tmp_path: Path, *, condition: AuditCondition, hooks: list | None):
    inner = InProcessMessageBus()
    alog = ActionLog(db_path=tmp_path / "run.db")
    slog = ShadowLog(db_path=tmp_path / "shadow.db")
    return inner, alog, AuditedMessageBus(
        inner=inner, action_log=alog, shadow_log=slog, condition=condition,
        hooks=hooks,
    )


async def test_baseline_skips_hooks(tmp_path: Path):
    inner, alog, bus = _make_bus(tmp_path, condition=AuditCondition.BASELINE,
                                  hooks=[StubRewriteHook()])
    await bus.send(sender_id="a", recipient_id="b", content="the secret is 42")
    # No policy_decision records under baseline
    assert not any(r.action_type == ActionType.POLICY_DECISION for r in alog.read_all())
    # Content delivered unchanged
    assert (await inner.recv(recipient_id="b")) == ("a", "the secret is 42")


async def test_passive_logs_but_does_not_rewrite(tmp_path: Path):
    inner, alog, bus = _make_bus(tmp_path, condition=AuditCondition.PASSIVE,
                                  hooks=[StubRewriteHook()])
    await bus.send(sender_id="a", recipient_id="b", content="the secret is 42")
    # Policy decision logged
    assert any(r.action_type == ActionType.POLICY_DECISION for r in alog.read_all())
    # Content delivered UNCHANGED (passive = log only)
    assert (await inner.recv(recipient_id="b")) == ("a", "the secret is 42")


async def test_enforce_rewrites_message(tmp_path: Path):
    inner, alog, bus = _make_bus(tmp_path, condition=AuditCondition.ENFORCE,
                                  hooks=[StubRewriteHook()])
    await bus.send(sender_id="a", recipient_id="b", content="the secret is 42")
    # Content delivered REWRITTEN
    assert (await inner.recv(recipient_id="b")) == ("a", "the [redacted] is 42")
    # Both the (rewritten) outbound AND the policy_decision appear in log
    rows = alog.read_all()
    action_types = [r.action_type for r in rows]
    assert ActionType.POLICY_DECISION in action_types
    assert ActionType.OUTBOUND_MESSAGE in action_types
    # The outbound_message row carries the rewritten content
    outbound_rows = [r for r in rows if r.action_type == ActionType.OUTBOUND_MESSAGE]
    assert outbound_rows[-1].payload["content"] == "the [redacted] is 42"


async def test_enforce_allows_when_no_hook_matches(tmp_path: Path):
    inner, alog, bus = _make_bus(tmp_path, condition=AuditCondition.ENFORCE,
                                  hooks=[StubRewriteHook()])
    await bus.send(sender_id="a", recipient_id="b", content="hello world")
    # ALLOW decision still logs a policy_decision + unchanged outbound
    assert (await inner.recv(recipient_id="b")) == ("a", "hello world")
    rows = alog.read_all()
    assert any(r.action_type == ActionType.POLICY_DECISION for r in rows)


async def test_enforce_blocks_swallows_outbound(tmp_path: Path):
    inner, alog, bus = _make_bus(tmp_path, condition=AuditCondition.ENFORCE,
                                  hooks=[StubBlockHook()])
    result = await bus.send(sender_id="a", recipient_id="b", content="BLOCKME")
    # No outbound delivered
    assert (await inner.recv(recipient_id="b")) is None
    # Policy decision logged but no outbound_message row
    rows = alog.read_all()
    action_types = [r.action_type for r in rows]
    assert ActionType.POLICY_DECISION in action_types
    assert ActionType.OUTBOUND_MESSAGE not in action_types
    # send returns empty string sentinel
    assert result == ""


async def test_no_hooks_behaves_as_before(tmp_path: Path):
    """When hooks is None or [], behavior is identical across all conditions."""
    for cond in (AuditCondition.BASELINE, AuditCondition.PASSIVE, AuditCondition.ENFORCE):
        inner, alog, bus = _make_bus(tmp_path / str(cond.value),
                                      condition=cond, hooks=None)
        await bus.send(sender_id="a", recipient_id="b", content="msg")
        rows = alog.read_all()
        assert all(r.action_type == ActionType.OUTBOUND_MESSAGE for r in rows)
        assert (await inner.recv(recipient_id="b")) == ("a", "msg")
