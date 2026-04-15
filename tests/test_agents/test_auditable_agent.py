from pathlib import Path

from clawsocialarena.action_log import ActionLog
from clawsocialarena.agents.auditable_agent import AuditableAIAgent
from clawsocialarena.agents.llm_client import MockLLMClient
from clawsocialarena.bus.audited import AuditedMessageBus
from clawsocialarena.bus.in_process import InProcessMessageBus
from clawsocialarena.types import AuditCondition


async def test_agent_responds_to_inbound(tmp_path: Path):
    inner_bus = InProcessMessageBus()
    log = ActionLog(db_path=tmp_path / "run.db")
    bus = AuditedMessageBus(inner=inner_bus, action_log=log, condition=AuditCondition.BASELINE)
    alice_llm = MockLLMClient(canned_responses=["Hello, bob!"])
    alice = AuditableAIAgent(agent_id="alice", llm=alice_llm, bus=bus, system_prompt="You are alice.")

    # No inbound yet -> step returns without sending
    handled = await alice.step()
    assert handled is False
    assert log.read_all() == []

    # Deliver a message to alice
    await inner_bus.send(sender_id="bob", recipient_id="alice", content="hi")
    handled = await alice.step()
    assert handled is True
    rows = log.read_all()
    assert len(rows) == 1
    assert rows[0].payload["recipient_id"] == "bob"
    assert "Hello" in rows[0].payload["content"]
