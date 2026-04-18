from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from clawsocialarena.types import ActionRecord


class PolicyVerdict(StrEnum):
    ALLOW = "allow"
    REWRITE = "rewrite"
    BLOCK = "block"


class PolicyDecision(BaseModel):
    verdict: PolicyVerdict
    rewritten_content: str | None = None
    rewritten_mentioned_items: list[str] | None = None
    reason: str | None = None
    policy_id: str | None = None


@runtime_checkable
class PolicyHook(Protocol):
    """Hook that evaluates an ActionRecord and returns a PolicyDecision.

    Hooks may additionally declare a ``hook_kind`` class attribute to scope
    which action types they fire on. The AuditedMessageBus convention:

    - ``hook_kind = "message"`` (default): fires on OUTBOUND_MESSAGE records
      (via ``bus.send``). This is the default for implementers that omit the
      attribute — e.g. ``StubRewriteHook``, ``RuleBasedDLP``.
    - ``hook_kind = "tool"``: fires on TOOL_CALL records (via
      ``bus.record_tool_call``). Message hooks are skipped for tool calls and
      vice-versa, so DLP-style content scanners don't accidentally evaluate
      tool arguments.

    The attribute is intentionally informal (runtime-checkable via
    ``getattr(hook, "hook_kind", "message")``) rather than part of the
    Protocol signature to keep existing hook implementations source-compatible.
    """

    def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
        ...
