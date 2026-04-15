"""In-process asyncio-backed MessageBus. Default transport for benchmark runs."""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict


class InProcessMessageBus:
    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)

    async def send(self, *, sender_id: str, recipient_id: str, content: str) -> str:
        action_id = f"act-{uuid.uuid4().hex[:12]}"
        await self._queues[recipient_id].put((sender_id, content))
        return action_id

    async def recv(self, *, recipient_id: str) -> tuple[str, str] | None:
        try:
            return self._queues[recipient_id].get_nowait()
        except asyncio.QueueEmpty:
            return None
