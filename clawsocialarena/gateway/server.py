"""aiohttp application factory and CLI entry point for the gateway.

:func:`build_app` takes a :class:`~clawsocialarena.gateway.session.Session`
and returns an aiohttp ``Application`` with the session stashed under
``app["session"]``. Handlers retrieve it via ``request.app["session"]``.

For local development the module is runnable:

    python -m clawsocialarena.gateway.server --condition baseline --port 8080

The CLI defaults to BASELINE so a standalone boot requires no database
path. Under PASSIVE or ENFORCE a ``--db-path`` argument is required so
the ``ActionLog`` and ``ShadowLog`` have somewhere to land.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from aiohttp import web

from clawsocialarena.gateway import routes
from clawsocialarena.gateway.session import Session
from clawsocialarena.types import AuditCondition


def build_app(session: Session) -> web.Application:
    """Build the aiohttp application with the gateway's HTTP routes.

    The ``session`` is stashed at ``app["session"]`` so handlers in
    :mod:`clawsocialarena.gateway.routes` can read it via
    ``request.app["session"]`` without a module-level global.
    """

    app = web.Application()
    app["session"] = session
    app.router.add_get("/healthz", routes.healthz)
    app.router.add_post("/send", routes.send)
    app.router.add_post("/recv", routes.recv)
    return app


def _build_default_session(args: argparse.Namespace) -> Session:
    """Build the Session for a standalone ``python -m`` boot from CLI args."""
    condition = AuditCondition(args.condition)
    if condition == AuditCondition.BASELINE:
        db_path = args.db_path or "/dev/null"
    else:
        if not args.db_path:
            raise SystemExit(
                f"--db-path is required when --condition={condition.value}"
            )
        db_path = args.db_path
    return Session.build(
        scenario_id=args.scenario_id,
        condition=condition,
        db_path=Path(db_path),
    )


def main(argv: list[str] | None = None) -> None:
    """Run the gateway server on a configurable host and port."""
    parser = argparse.ArgumentParser(prog="clawsocialarena.gateway.server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080).")
    parser.add_argument(
        "--condition",
        default=AuditCondition.BASELINE.value,
        choices=[c.value for c in AuditCondition],
        help="Audit condition for the default Session (default: baseline).",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Primary ActionLog DB path; required under passive/enforce.",
    )
    parser.add_argument(
        "--scenario-id",
        default="gateway-default",
        help="Scenario id to assign to the default Session.",
    )
    args = parser.parse_args(argv)

    session = _build_default_session(args)
    app = build_app(session)
    web.run_app(app, host=args.host, port=args.port)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
