"""Minimal AuditableAIAgent with tool dispatch support.

Reads inbound from the bus, calls the LLM, dispatches any tool_calls (logging
TOOL_CALL + TOOL_OBSERVATION_RETURN records THROUGH the bus so condition
gating, shadow double-write, hook evaluation, and phase tagging all apply),
re-invokes the LLM with tool outputs injected as tool-role messages, and
finally sends the assistant's content as an outbound via the bus.

Hermes full integration is future work per spec Section 7.4; a Hermes adapter
can slot in later via the same LLMClient + MessageBus interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from clawsocialarena.agents.llm_client import LLMClient, LLMMessage
from clawsocialarena.agents.tools import ToolRegistry
from clawsocialarena.protocols import MessageBus


@dataclass
class AuditableAIAgent:
    agent_id: str
    llm: LLMClient
    bus: MessageBus
    system_prompt: str
    tools: ToolRegistry | None = None
    _history: list[LLMMessage] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._history.append(LLMMessage(role="system", content=self.system_prompt))

    async def step(self) -> bool:
        """Process one inbound message if available. Returns True if a message was handled."""
        msg = await self.bus.recv(recipient_id=self.agent_id)
        if msg is None:
            return False
        sender_id, content = msg
        self._history.append(LLMMessage(role="user", content=f"[from {sender_id}] {content}"))

        max_tool_rounds = 5
        for _ in range(max_tool_rounds):
            completion = self.llm.complete(
                messages=list(self._history),
                tools=self._tool_schemas() if self.tools else None,
                params={},
            )
            if not completion.tool_calls:
                # No more tools; send final content and stop
                self._history.append(LLMMessage(role="assistant", content=completion.content))
                await self.bus.send(
                    sender_id=self.agent_id,
                    recipient_id=sender_id,
                    content=completion.content,
                )
                return True

            # Dispatch every tool_call — logging now flows through the bus so
            # AuditedMessageBus can apply condition gating + shadow writes +
            # phase tagging; under baseline (RawMessageBus) these are no-ops.
            for tc in completion.tool_calls:
                tool_name = tc.get("name", "")
                args = tc.get("arguments", {})
                tc_action_id = await self.bus.record_tool_call(
                    agent_id=self.agent_id,
                    tool_name=tool_name,
                    arguments=args,
                )
                observation = ""
                if self.tools is not None:
                    try:
                        tool = self.tools.get(tool_name)
                        observation = tool.invoke(args)
                    except KeyError:
                        observation = f"[error] unknown tool '{tool_name}'"
                await self.bus.record_tool_observation(
                    agent_id=self.agent_id,
                    tool_call_action_id=tc_action_id,
                    tool_name=tool_name,
                    observation=observation,
                )
                # Inject observation back into history so the next LLM call sees it
                self._history.append(
                    LLMMessage(role="tool", content=f"[tool:{tool_name}] {observation}")
                )

        # Exceeded tool rounds; fall through with empty assistant turn
        self._history.append(LLMMessage(role="assistant", content=""))
        return True

    def _tool_schemas(self) -> list[dict]:
        assert self.tools is not None  # guarded by caller
        return [
            {"name": t, "schema": self.tools.get(t).schema}
            for t in self.tools.list_names()
        ]
