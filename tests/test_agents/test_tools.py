from pathlib import Path

from clawsocialarena.action_log import ActionLog
from clawsocialarena.agents.auditable_agent import AuditableAIAgent
from clawsocialarena.agents.llm_client import LLMCompletion
from clawsocialarena.agents.tools import EchoTool, ToolRegistry
from clawsocialarena.bus.audited import AuditedMessageBus
from clawsocialarena.bus.in_process import InProcessMessageBus
from clawsocialarena.types import ActionType, AuditCondition


def test_tool_registry_lookup():
    reg = ToolRegistry()
    reg.register(EchoTool())
    assert reg.get("echo").name == "echo"
    assert reg.list_names() == ["echo"]


def test_echo_tool_invocation():
    echo = EchoTool()
    assert echo.invoke({"text": "hello"}) == "hello"


class ScriptedToolLLM:
    """LLM that returns a tool_call on first .complete, then plain text on second."""

    def __init__(self) -> None:
        self._i = 0

    def complete(self, *, messages, tools, params):
        self._i += 1
        if self._i == 1:
            return LLMCompletion(
                content="",
                tool_calls=[{"id": "tc1", "name": "echo", "arguments": {"text": "hi from tool"}}],
            )
        return LLMCompletion(content="done: tool said hi from tool")


async def test_agent_dispatches_tool_and_logs_actions(tmp_path: Path):
    inner = InProcessMessageBus()
    log = ActionLog(db_path=tmp_path / "run.db")
    bus = AuditedMessageBus(inner=inner, action_log=log, condition=AuditCondition.BASELINE)
    reg = ToolRegistry()
    reg.register(EchoTool())

    alice = AuditableAIAgent(
        agent_id="alice",
        llm=ScriptedToolLLM(),
        bus=bus,
        system_prompt="sys",
        tools=reg,
        action_log=log,
    )
    # Inject a message to alice so she responds (and uses a tool during her turn)
    await inner.send(sender_id="bob", recipient_id="alice", content="please ping")
    await alice.step()

    rows = log.read_all()
    action_types = [r.action_type for r in rows]
    assert ActionType.TOOL_CALL in action_types
    assert ActionType.TOOL_OBSERVATION_RETURN in action_types
    assert ActionType.OUTBOUND_MESSAGE in action_types
