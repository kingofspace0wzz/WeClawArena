"""In-gateway MCP host that multiplexes tool handlers by name.

The host keeps a simple name-to-handler table and dispatches a
``tool_name`` + ``arguments`` pair to the registered callable. Handlers
may be plain callables returning a dict, or async functions returning a
dict; :meth:`McpHost.dispatch` awaits the coroutine form and wraps the
plain form uniformly.

One :class:`McpHost` lives on each :class:`Session` so scenario setup
code can register scenario-specific tools (calendar, ledger, etc.)
against a well-known host reachable via ``POST /mcp/{tool_name}``. The
HTTP wiring is implemented in :mod:`clawsocialarena.gateway.routes`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

ToolHandler = Callable[[dict], "Awaitable[dict] | dict"]

_logger = logging.getLogger(__name__)


class McpHost:
    """Registry of MCP tool handlers keyed by ``tool_name``.

    The host is intentionally minimal: no schema validation, no JSON-RPC
    framing, no transport layer. Scenario code registers a callable for
    each tool it wants to expose, and the gateway route calls
    :meth:`dispatch` per incoming request. The route layer is responsible
    for recording ``TOOL_CALL`` + ``TOOL_OBSERVATION_RETURN`` actions on
    the session.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, tool_name: str, handler: ToolHandler) -> None:
        """Register ``handler`` under ``tool_name``; overwrite silently.

        Re-registration is allowed because scenario setup can rebuild a
        host between runs. When the name already exists a debug-level
        log line records the overwrite so diagnostics can trace why a
        given call hit a different implementation than expected.
        """

        if tool_name in self._handlers:
            _logger.debug("McpHost: overwriting handler for tool_name=%s", tool_name)
        self._handlers[tool_name] = handler

    async def dispatch(self, tool_name: str, arguments: dict) -> dict:
        """Invoke the registered handler for ``tool_name`` with ``arguments``.

        Coroutine handlers are awaited; plain callables are invoked
        directly. Either way the return value must be a ``dict``. Raises
        ``KeyError`` when no handler is registered for ``tool_name`` so
        the HTTP layer can translate that into a 404 response.
        """

        if tool_name not in self._handlers:
            raise KeyError(tool_name)
        handler = self._handlers[tool_name]
        if asyncio.iscoroutinefunction(handler):
            result: Any = await handler(arguments)
        else:
            result = handler(arguments)
            if asyncio.iscoroutine(result):
                # Handler is a non-async callable that returned a coroutine.
                # Await it so the caller always sees a concrete dict.
                result = await result
        if not isinstance(result, dict):
            raise TypeError(
                f"MCP handler for {tool_name!r} returned {type(result).__name__}, expected dict"
            )
        return result

    def tools(self) -> list[str]:
        """Return the list of currently registered tool names."""

        return list(self._handlers.keys())
