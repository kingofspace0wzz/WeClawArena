"""HTTP route handlers for the gateway.

Subsequent tasks (A3) will extend this module with ``/send`` and ``/recv``
handlers. For Task A1 only the liveness probe is implemented.
"""

from __future__ import annotations

from aiohttp import web


async def healthz(_request: web.Request) -> web.Response:
    """Liveness probe: returns ``{"ok": true}`` with HTTP 200."""
    return web.json_response({"ok": True})
