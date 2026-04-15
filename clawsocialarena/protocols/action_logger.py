from typing import Protocol, runtime_checkable

from clawsocialarena.types import ActionRecord


@runtime_checkable
class ActionLogger(Protocol):
    def append(self, rec: ActionRecord) -> str:
        """Append an immutable action record; returns its hash."""
        ...
