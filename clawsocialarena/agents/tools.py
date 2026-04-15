"""Tool protocol + registry + trivial EchoTool for tests.

Phase 3 Task 3.3 adds native tool dispatch to ``AuditableAIAgent`` instead of
wrapping Hermes. This module defines the minimal surface the agent needs:
a ``Tool`` Protocol (name/schema/invoke), a ``ToolRegistry`` keyed by name,
and an ``EchoTool`` used by tests. Future work per spec Section 7.4 may
substitute a Hermes-backed adapter at this same boundary.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Tool(Protocol):
    """A named, schema-described callable invocable by the agent."""

    name: str
    schema: dict

    def invoke(self, arguments: dict) -> str: ...


class ToolRegistry:
    """Simple in-memory registry mapping tool name to Tool."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def list_names(self) -> list[str]:
        return list(self._tools.keys())


class EchoTool:
    """Trivial tool that returns its ``text`` argument verbatim."""

    name = "echo"
    schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def invoke(self, arguments: dict) -> str:
        return str(arguments.get("text", ""))
