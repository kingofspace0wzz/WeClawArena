from typing import Protocol, runtime_checkable


@runtime_checkable
class MessageBus(Protocol):
    """Transport for agent-to-agent messages within a scenario run."""

    async def send(self, *, sender_id: str, recipient_id: str, content: str) -> str:
        """Send `content` from `sender_id` to `recipient_id`. Returns action_id."""
        ...

    async def recv(self, *, recipient_id: str) -> tuple[str, str] | None:
        """Receive the next queued message for `recipient_id`. Returns (sender_id, content) or None."""
        ...
