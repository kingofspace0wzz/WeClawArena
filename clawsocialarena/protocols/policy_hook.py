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
    reason: str | None = None
    policy_id: str | None = None


@runtime_checkable
class PolicyHook(Protocol):
    def evaluate(self, *, action: ActionRecord, context: dict) -> PolicyDecision:
        ...
