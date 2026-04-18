"""Scenario-specific MCP tool implementations for ClawSocialArena v2.

Each tool is a callable ``async def tool(arguments: dict) -> dict`` (or
the synchronous equivalent) that the gateway :class:`~clawsocialarena.
gateway.mcp_host.McpHost` dispatches to. The ``noop`` tool is the
minimal stub used by Task A6 to validate the dispatch and audit path.
"""

from __future__ import annotations

from .noop import noop

__all__ = ["noop"]
