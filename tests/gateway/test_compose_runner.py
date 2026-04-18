"""Unit tests for :mod:`clawsocialarena.gateway.compose_runner`.

These tests do not need a Docker engine and therefore run on any
machine. The E2E path that actually brings a compose up lives in
``tests/e2e/test_compose_up_down.py`` and self-skips when Docker is
missing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.gateway import compose_runner
from clawsocialarena.gateway.compose_runner import (
    ComposeHandle,
    ComposeRunner,
    DockerUnavailable,
    docker_available,
)


def test_docker_unavailable_is_runtime_error_subclass() -> None:
    """``DockerUnavailable`` is a :class:`RuntimeError` so generic except handlers catch it."""

    assert issubclass(DockerUnavailable, RuntimeError)


def test_compose_handle_dataclass_fields() -> None:
    """:class:`ComposeHandle` exposes the three fields callers read."""

    handle = ComposeHandle(
        gateway_url="http://localhost:8080",
        project_name="demo",
        template_path=Path("/tmp/fake.yml"),
    )
    assert handle.gateway_url == "http://localhost:8080"
    assert handle.project_name == "demo"
    assert handle.template_path == Path("/tmp/fake.yml")


def test_compose_runner_raises_when_docker_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Construction raises :class:`DockerUnavailable` when ``shutil.which`` returns ``None``.

    The context manager protocol of :class:`ComposeRunner` means the
    ``DockerUnavailable`` fires the moment the generator body starts
    executing, so entering the ``with`` block is what we test against.
    """

    # Patch the ``shutil`` reference inside the compose_runner module so
    # we do not disturb anything else that imports ``shutil.which``.
    monkeypatch.setattr(compose_runner.shutil, "which", lambda _name: None)
    assert docker_available() is False

    with pytest.raises(DockerUnavailable):
        with ComposeRunner(Path("/does/not/matter.yml")):
            pytest.fail("ComposeRunner should have raised before yielding")


def test_docker_available_returns_true_when_shutil_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """:func:`docker_available` returns ``True`` when ``shutil.which`` resolves a path."""

    monkeypatch.setattr(compose_runner.shutil, "which", lambda _name: "/usr/local/bin/docker")
    assert docker_available() is True
