"""Compose-level scenario driver for ClawSocialArena.

:class:`ComposeRunner` wraps ``docker compose up`` / ``docker compose down``
for a scenario template, waits for the gateway container to report healthy
on ``/healthz``, yields a :class:`ComposeHandle` for the duration of the
scenario, and tears the compose project back down on exit.

The runner is used as a context manager:

.. code-block:: python

    from pathlib import Path
    from clawsocialarena.gateway.compose_runner import ComposeRunner

    template = Path("docker/compose-templates/minimal.yml")
    with ComposeRunner(template) as handle:
        assert handle.gateway_url.startswith("http://")

Docker is not a hard dependency of the Python package: when the
``docker`` binary is absent, :func:`docker_available` returns ``False`` and
constructing the runner raises :class:`DockerUnavailable`. That keeps the
unit test suite green on machines without Docker, while the E2E test
module is guarded by a pytest skip at import time.

``subprocess`` is used instead of ``python-on-whales`` to avoid an extra
runtime dependency; the surface we need (compose up, compose down, and
HTTP health polling) is a small enough command-line footprint that the
wrapper stays readable.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Generator


class DockerUnavailable(RuntimeError):
    """Raised when :class:`ComposeRunner` cannot find the ``docker`` CLI.

    Callers in test suites should catch this and skip; production callers
    should treat it as a configuration error.
    """


@dataclass
class ComposeHandle:
    """Handle yielded by :class:`ComposeRunner` while the compose is up.

    Attributes:
        gateway_url: Host-side URL the gateway can be reached at (for
            example ``http://localhost:8080``). Strip any trailing slash;
            concrete routes append their own path.
        project_name: The ``docker compose -p`` project name; useful for
            debugging with ``docker compose -p <name> ps``.
        template_path: Absolute path to the compose template that was
            brought up, stashed so callers do not have to thread it
            through separately.
    """

    gateway_url: str
    project_name: str
    template_path: Path


def docker_available() -> bool:
    """Return ``True`` if the ``docker`` CLI is reachable on ``PATH``.

    This is a cheap check that does not touch the daemon; callers that
    need a live daemon should additionally run ``docker info``. For the
    test-suite skip guard, a reachable binary is what we care about.
    """

    return shutil.which("docker") is not None


def _wait_for_healthz(url: str, timeout: float = 60.0) -> None:
    """Poll ``{url}/healthz`` until it returns HTTP 200 or ``timeout`` elapses.

    Raises :class:`TimeoutError` if the endpoint never responds in time.
    A 0.5s sleep between attempts keeps the loop from hammering the
    daemon while the gateway container is still starting up.
    """

    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url + "/healthz", timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - exercised at runtime
            last_exc = exc
        time.sleep(0.5)
    raise TimeoutError(
        f"Gateway at {url} did not become healthy within {timeout}s"
        + (f" (last error: {last_exc!r})" if last_exc else "")
    )


@contextlib.contextmanager
def ComposeRunner(
    template_path: Path,
    *,
    project_name: str = "clawsocial-dev",
    env: dict[str, str] | None = None,
    gateway_port: int = 8080,
    health_timeout: float = 60.0,
) -> Generator[ComposeHandle, None, None]:
    """Bring up a compose template, yield a :class:`ComposeHandle`, tear down.

    Args:
        template_path: Path to the compose file (for example
            ``docker/compose-templates/minimal.yml``).
        project_name: Passed to ``docker compose -p``. A fixed project
            name lets the teardown clean up the same resources the setup
            created even if ``__exit__`` runs in a different cwd.
        env: Extra environment variables forwarded to the ``docker``
            subprocess. Useful for substituting ``$VAR`` references
            inside the compose template.
        gateway_port: Host port the gateway is published on. Must match
            the ``ports:`` block in the template.
        health_timeout: Seconds to wait for ``/healthz`` before giving up.

    Raises:
        DockerUnavailable: If ``docker`` is not on ``PATH``.
        subprocess.CalledProcessError: If ``docker compose up`` fails.
        TimeoutError: If the gateway never reports healthy.
    """

    if not docker_available():
        raise DockerUnavailable("docker is not on PATH")

    template_path = Path(template_path)
    up_cmd = [
        "docker",
        "compose",
        "-f",
        str(template_path),
        "-p",
        project_name,
        "up",
        "-d",
    ]
    subprocess.run(up_cmd, check=True, env=env)
    try:
        url = f"http://localhost:{gateway_port}"
        _wait_for_healthz(url, timeout=health_timeout)
        yield ComposeHandle(
            gateway_url=url,
            project_name=project_name,
            template_path=template_path,
        )
    finally:
        # ``-v`` drops any named volumes the compose created so rerunning
        # the test does not inherit stale state. ``check=False`` keeps
        # teardown best-effort: if setup raised before the compose was
        # fully up, there may be nothing to tear down and that is fine.
        down_cmd = [
            "docker",
            "compose",
            "-f",
            str(template_path),
            "-p",
            project_name,
            "down",
            "-v",
        ]
        subprocess.run(down_cmd, check=False)
