from pathlib import Path

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.phase_tracker import PhaseTracker
from clawsocialarena.bus.audited import AuditedMessageBus
from clawsocialarena.bus.in_process import InProcessMessageBus
from clawsocialarena.types import AuditCondition, ActionType


async def test_send_writes_action_log(tmp_path: Path):
    inner = InProcessMessageBus()
    log = ActionLog(db_path=tmp_path / "run.db")
    bus = AuditedMessageBus(inner=inner, action_log=log, condition=AuditCondition.BASELINE)
    await bus.send(sender_id="alice", recipient_id="bob", content="hi")
    rows = log.read_all()
    assert len(rows) == 1
    assert rows[0].action_type == ActionType.OUTBOUND_MESSAGE
    assert rows[0].agent_id == "alice"
    assert rows[0].payload == {"recipient_id": "bob", "content": "hi"}


async def test_forwards_to_inner_bus(tmp_path: Path):
    inner = InProcessMessageBus()
    log = ActionLog(db_path=tmp_path / "run.db")
    bus = AuditedMessageBus(inner=inner, action_log=log, condition=AuditCondition.BASELINE)
    await bus.send(sender_id="alice", recipient_id="bob", content="hello")
    msg = await inner.recv(recipient_id="bob")
    assert msg == ("alice", "hello")


async def test_bus_tags_record_with_tracker_phase(tmp_path: Path):
    inner = InProcessMessageBus()
    log = ActionLog(db_path=tmp_path / "run.db")
    tracker = PhaseTracker.from_schedule([
        {"phase": "discovery", "start_turn": 0, "end_turn": 1},
        {"phase": "negotiation", "start_turn": 1, "end_turn": 10},
    ])
    tracker.advance_to_turn(3)
    bus = AuditedMessageBus(
        inner=inner, action_log=log, condition=AuditCondition.BASELINE, phase_tracker=tracker
    )
    await bus.send(sender_id="alice", recipient_id="bob", content="hello")
    rows = log.read_all()
    assert rows[0].social_phase.value == "negotiation"
