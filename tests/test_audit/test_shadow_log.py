from pathlib import Path

from clawsocialarena.action_log import ActionLog
from clawsocialarena.audit.shadow_log import ShadowLog
from clawsocialarena.bus.audited import AuditedMessageBus
from clawsocialarena.bus.in_process import InProcessMessageBus
from clawsocialarena.types import AuditCondition


async def test_shadow_log_mirrors_action_log(tmp_path: Path):
    alog = ActionLog(db_path=tmp_path / "run.db")
    slog = ShadowLog(db_path=tmp_path / "shadow.db")
    bus = AuditedMessageBus(
        inner=InProcessMessageBus(),
        action_log=alog,
        shadow_log=slog,
        condition=AuditCondition.BASELINE,
    )
    await bus.send(sender_id="a", recipient_id="b", content="hi")
    await bus.send(sender_id="a", recipient_id="b", content="again")
    assert len(alog.read_all()) == 2
    assert len(slog.read_all()) == 2
    # Actions match by content in both logs
    contents_alog = [r.payload["content"] for r in alog.read_all()]
    contents_slog = [r.payload["content"] for r in slog.read_all()]
    assert contents_alog == contents_slog == ["hi", "again"]


async def test_shadow_log_has_own_chain(tmp_path: Path):
    alog = ActionLog(db_path=tmp_path / "run.db")
    slog = ShadowLog(db_path=tmp_path / "shadow.db")
    bus = AuditedMessageBus(
        inner=InProcessMessageBus(),
        action_log=alog,
        shadow_log=slog,
        condition=AuditCondition.BASELINE,
    )
    await bus.send(sender_id="a", recipient_id="b", content="one")
    # Both logs verify independently
    assert alog.verify_chain("a") is True
    assert slog.verify_chain("a") is True
