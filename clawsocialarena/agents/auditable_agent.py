"""Minimal AuditableAIAgent with tool dispatch support.

Reads inbound from the bus, calls the LLM, dispatches any tool_calls (logging
TOOL_CALL + TOOL_OBSERVATION_RETURN records), re-invokes the LLM with tool
outputs injected as tool-role messages, and finally sends the assistant's
content as an outbound via the bus.

Hermes full integration is future work per spec Section 7.4; a Hermes adapter
can slot in later via the same LLMClient + MessageBus interfaces.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from clawsocialarena.action_log import ActionLog
from clawsocialarena.agents.llm_client import LLMClient, LLMMessage
from clawsocialarena.agents.tools import ToolRegistry
from clawsocialarena.protocols import MessageBus
from clawsocialarena.types import (
    ActionRecord,
    ActionType,
    ExecutionPhase,
    IntegrityLevel,
    SocialPhase,
)


@dataclass
class AuditableAIAgent:
    agent_id: str
    llm: LLMClient
    bus: MessageBus
    system_prompt: str
    tools: ToolRegistry | None = None
    action_log: ActionLog | None = None
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

            # Dispatch every tool_call
            for tc in completion.tool_calls:
                self._log_tool_call(tc)
                tool_name = tc.get("name", "")
                args = tc.get("arguments", {})
                observation = ""
                if self.tools is not None:
                    try:
                        tool = self.tools.get(tool_name)
                        observation = tool.invoke(args)
                    except KeyError:
                        observation = f"[error] unknown tool '{tool_name}'"
                self._log_tool_observation(tc.get("id", ""), tool_name, observation)
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

    def _log_tool_call(self, tc: dict) -> None:
        if self.action_log is None:
            return
        rec = ActionRecord(
            action_id=f"tc-{uuid.uuid4().hex[:12]}",
            prev_hash=self.action_log.head_hash(self.agent_id),
            agent_id=self.agent_id,
            action_type=ActionType.TOOL_CALL,
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=SocialPhase.DISCOVERY,
            payload={"tool_name": tc.get("name"), "arguments": tc.get("arguments", {})},
            integrity_level=IntegrityLevel.HASH_CHAINED,
        )
        self.action_log.append(rec)

    def _log_tool_observation(self, tool_call_id: str, tool_name: str, observation: str) -> None:
        if self.action_log is None:
            return
        rec = ActionRecord(
            action_id=f"tr-{uuid.uuid4().hex[:12]}",
            prev_hash=self.action_log.head_hash(self.agent_id),
            agent_id=self.agent_id,
            action_type=ActionType.TOOL_OBSERVATION_RETURN,
            timestamp=datetime.now(timezone.utc).isoformat(),
            execution_phase=ExecutionPhase.NOMINAL,
            social_phase=SocialPhase.DISCOVERY,
            payload={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "observation": observation,
            },
            integrity_level=IntegrityLevel.HASH_CHAINED,
        )
        self.action_log.append(rec)
