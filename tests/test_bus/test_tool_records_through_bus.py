from pathlib import Path

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.shadow_log import ShadowLog
from clawsocialarena.bus.audited import AuditedMessageBus
from clawsocialarena.bus.in_process import InProcessMessageBus
from clawsocialarena.types import ActionType, AuditCondition


def _mk_bus(tmp_path: Path, cond: AuditCondition):
    alog = ActionLog(db_path=tmp_path / "run.db")
    slog = ShadowLog(db_path=tmp_path / "shadow.db")
    inner = InProcessMessageBus()
    bus = AuditedMessageBus(
        inner=inner, action_log=alog, shadow_log=slog, condition=cond
    )
    return bus, alog, slog


async def test_record_tool_call_writes_primary_and_shadow(tmp_path: Path):
    bus, alog, slog = _mk_bus(tmp_path, AuditCondition.PASSIVE)
    action_id = await bus.record_tool_call(
        agent_id="alice", tool_name="echo", arguments={"text": "hi"}
    )
    assert action_id.startswith("act-") or action_id.startswith("tc-")
    pri = alog.read_all()
    sha = slog.read_all()
    assert any(r.action_type == ActionType.TOOL_CALL for r in pri)
    assert any(r.action_type == ActionType.TOOL_CALL for r in sha)
    # The action_id returned matches the one in the log
    assert any(r.action_id == action_id for r in pri)


async def test_record_tool_observation_links_to_tool_call(tmp_path: Path):
    bus, alog, slog = _mk_bus(tmp_path, AuditCondition.PASSIVE)
    tc_id = await bus.record_tool_call(
        agent_id="alice", tool_name="echo", arguments={"text": "hi"}
    )
    obs_id = await bus.record_tool_observation(
        agent_id="alice",
        tool_call_action_id=tc_id,
        tool_name="echo",
        observation="hi back",
    )
    rows = alog.read_all()
    obs_rows = [r for r in rows if r.action_type == ActionType.TOOL_OBSERVATION_RETURN]
    assert len(obs_rows) == 1
    assert obs_rows[0].payload["tool_call_action_id"] == tc_id
    assert obs_rows[0].payload["tool_name"] == "echo"
    assert obs_rows[0].payload["observation"] == "hi back"


async def test_tool_records_tagged_with_phase(tmp_path: Path):
    from clawsocialarena.audit.phase_tracker import PhaseTracker
    from clawsocialarena.types import SocialPhase
    pt = PhaseTracker.from_schedule([
        {"phase": "negotiation", "start_turn": 0, "end_turn": 10}
    ])
    pt.advance_to_turn(0)
    alog = ActionLog(db_path=tmp_path / "run.db")
    slog = ShadowLog(db_path=tmp_path / "shadow.db")
    bus = AuditedMessageBus(
        inner=InProcessMessageBus(),
        action_log=alog,
        shadow_log=slog,
        condition=AuditCondition.PASSIVE,
        phase_tracker=pt,
    )
    await bus.record_tool_call(agent_id="alice", tool_name="echo", arguments={})
    rows = alog.read_all()
    tc = next(r for r in rows if r.action_type == ActionType.TOOL_CALL)
    assert tc.social_phase == SocialPhase.NEGOTIATION


async def test_tool_hooks_fire_only_on_tool_kind(tmp_path: Path):
    """Message hooks should NOT evaluate tool_call records."""
    from clawsocialarena.protocols import PolicyDecision, PolicyVerdict
    from clawsocialarena.types import ActionRecord

    call_count = {"n": 0}

    class NoisyMessageHook:
        hook_kind = "message"

        def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
            call_count["n"] += 1
            return PolicyDecision(verdict=PolicyVerdict.ALLOW)

    bus, alog, _slog = _mk_bus(tmp_path, AuditCondition.PASSIVE)
    bus._hooks = [NoisyMessageHook()]
    # Send a message — should trigger the hook once
    await bus.send(sender_id="alice", recipient_id="bob", content="hi")
    # Record a tool call — should NOT trigger the message hook
    await bus.record_tool_call(agent_id="alice", tool_name="echo", arguments={})
    assert call_count["n"] == 1
