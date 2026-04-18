"""aiohttp application factory and CLI entry point for the gateway.

Only :func:`build_app` is intended to be wired up by tests. ``main`` is a
thin wrapper around :func:`aiohttp.web.run_app` for local development:

    python -m clawsocialarena.gateway.server --port 8080
"""

from __future__ import annotations

import argparse

from aiohttp import web

from clawsocialarena.gateway import routes


def build_app() -> web.Application:
    """Build the aiohttp application with the gateway's HTTP routes."""
    app = web.Application()
    app.router.add_get("/healthz", routes.healthz)
    return app


def main(argv: list[str] | None = None) -> None:
    """Run the gateway server on a configurable host and port."""
    parser = argparse.ArgumentParser(prog="clawsocialarena.gateway.server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080).")
    args = parser.parse_args(argv)

    app = build_app()
    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
