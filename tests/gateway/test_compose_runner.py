"""Unit tests for :mod:`clawsocialarena.gateway.compose_runner`.

These tests do not need a Docker engine and therefore run on any
machine. The E2E path that actually brings a compose up lives in
``tests/e2e/test_compose_up_down.py`` and self-skips when Docker is
missing.
"""

from __future__ import annotations

import subprocess
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


def test_compose_runner_rebuilds_images_before_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(compose_runner.shutil, "which", lambda _name: "/usr/local/bin/docker")
    monkeypatch.setattr(compose_runner, "_wait_for_healthz", lambda *_args, **_kwargs: None)
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs) -> None:
        calls.append(cmd)

    monkeypatch.setattr(compose_runner.subprocess, "run", fake_run)

    with ComposeRunner(Path("/tmp/docker-compose.yml"), project_name="demo"):
        pass

    assert calls[0] == [
        "docker",
        "compose",
        "-f",
        "/tmp/docker-compose.yml",
        "-p",
        "demo",
        "up",
        "--build",
        "-d",
    ]


def test_compose_runner_can_skip_rebuilds_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(compose_runner.shutil, "which", lambda _name: "/usr/local/bin/docker")
    monkeypatch.setattr(compose_runner, "_wait_for_healthz", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("CLAWSOCIALARENA_COMPOSE_BUILD", "0")
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs) -> None:
        calls.append(cmd)

    monkeypatch.setattr(compose_runner.subprocess, "run", fake_run)

    with ComposeRunner(Path("/tmp/docker-compose.yml"), project_name="demo"):
        pass

    assert calls[0] == [
        "docker",
        "compose",
        "-f",
        "/tmp/docker-compose.yml",
        "-p",
        "demo",
        "up",
        "--no-build",
        "-d",
    ]


def test_compose_runner_tears_down_when_up_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(compose_runner.shutil, "which", lambda _name: "/usr/local/bin/docker")
    calls: list[tuple[list[str], dict]] = []

    def fake_run(cmd: list[str], **kwargs) -> None:
        calls.append((cmd, kwargs))
        if "up" in cmd:
            raise subprocess.CalledProcessError(returncode=1, cmd=cmd)

    monkeypatch.setattr(compose_runner.subprocess, "run", fake_run)

    with pytest.raises(subprocess.CalledProcessError):
        with ComposeRunner(Path("/tmp/docker-compose.yml"), project_name="demo"):
            pytest.fail("ComposeRunner should not yield when compose up fails")

    assert calls[0][0] == [
        "docker",
        "compose",
        "-f",
        "/tmp/docker-compose.yml",
        "-p",
        "demo",
        "up",
        "--build",
        "-d",
    ]
    assert calls[1][0] == [
        "docker",
        "compose",
        "-f",
        "/tmp/docker-compose.yml",
        "-p",
        "demo",
        "down",
        "-v",
    ]
    assert calls[1][1]["check"] is False
