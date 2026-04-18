"""A trivial no-op MCP tool.

The ``noop`` tool returns ``{"ok": True, "echo": arguments}``. It exists
so the Task A6 wiring has something concrete to register, dispatch, and
audit without pulling in any scenario-specific state. Later tasks
replace or augment this with the real calendar, ledger, runbook, etc.
tools.
"""

from __future__ import annotations


async def noop(arguments: dict) -> dict:
    """Return ``{"ok": True, "echo": arguments}`` verbatim.

    The echo field lets tests assert that argument plumbing survives the
    round trip through the gateway's JSON decode, :class:`McpHost`
    dispatch, and JSON encode path.
    """

    return {"ok": True, "echo": arguments}
