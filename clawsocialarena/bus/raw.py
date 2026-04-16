"""RawMessageBus — no hash-chaining, no hooks, no shadow log.

Per spec §5.1, the baseline condition models a deployment WITHOUT audit
infrastructure. Using AuditedMessageBus under baseline means the ablation
pays the audit logging cost even when audit is "off" — this bus removes
that confound.

The bus keeps a lightweight `sent_history` so the runner can reconstruct
terminal-predicate signals (e.g. [READY_TO_PIN ...] tags) without any
ActionLog/ShadowLog infrastructure.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict


class RawMessageBus:
    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        # (sender_id, recipient_id, content) — used by the runner under baseline
        # to scan for terminal-predicate markers without an ActionLog.
        self.sent_history: list[tuple[str, str, str]] = []

    async def send(self, *, sender_id: str, recipient_id: str, content: str) -> str:
        action_id = f"raw-{uuid.uuid4().hex[:12]}"
        self.sent_history.append((sender_id, recipient_id, content))
        await self._queues[recipient_id].put((sender_id, content))
        return action_id

    async def recv(self, *, recipient_id: str) -> tuple[str, str] | None:
        try:
            return self._queues[recipient_id].get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def record_tool_call(
        self, *, agent_id: str, tool_name: str, arguments: dict
    ) -> str:
        # No-op under baseline: no ActionLog exists, so nothing to record.
        # Returning "" keeps AuditableAIAgent's control flow uniform across
        # baseline vs passive/enforce.
        return ""

    async def record_tool_observation(
        self,
        *,
        agent_id: str,
        tool_call_action_id: str,
        tool_name: str,
        observation: str,
    ) -> str:
        return ""
