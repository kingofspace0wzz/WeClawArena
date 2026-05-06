"""End-to-end checks for generated scenario compose bundles."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from clawsocialarena.gateway.compose_runner import ComposeRunner, docker_available


pytestmark = pytest.mark.skipif(
    not docker_available(), reason="docker not installed on this host"
)


def test_generated_compose_keeps_agent_containers_running() -> None:
    template = (
        Path(__file__).resolve().parents[2]
        / "benchmark"
        / "scenarios"
        / "v1.0.0"
        / "main"
        / "cu-scheduling-benign-01200"
        / "docker-compose.yml"
    )
    assert template.exists(), f"generated compose missing at {template}"

    with ComposeRunner(
        template,
        project_name="clawsocial-generated-e2e",
        gateway_port=8080,
        health_timeout=60,
    ) as handle:
        time.sleep(5)
        result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(template),
                "-p",
                handle.project_name,
                "ps",
                "--status",
                "running",
                "--services",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    running = set(result.stdout.splitlines())
    assert {"gateway", "alice", "bob"} <= running
