"""End-to-end test that the minimal compose template boots under :class:`ComposeRunner`.

The test is marked as skipped when Docker is not installed so the rest
of the suite stays green on machines without a Docker engine. When
Docker is available the test builds the two images from the worktree,
brings the compose up, waits for the gateway's ``/healthz`` endpoint to
return 200, and tears the compose back down on exit.

The first invocation on a fresh host will block on ``docker build`` for
both images; subsequent runs reuse the build cache. Budget several
minutes for the cold-start case.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.gateway.compose_runner import ComposeRunner, docker_available


pytestmark = pytest.mark.skipif(
    not docker_available(), reason="docker not installed on this host"
)


def test_compose_up_down() -> None:
    """Bring the minimal template up, assert the gateway is healthy, tear down."""

    # ``parents[2]`` walks from ``tests/e2e/test_compose_up_down.py`` up to
    # the worktree root. Keeping the resolution local to the test keeps
    # the fixture surface small.
    template = (
        Path(__file__).resolve().parents[2]
        / "docker"
        / "compose-templates"
        / "minimal.yml"
    )
    assert template.exists(), f"minimal compose template missing at {template}"

    with ComposeRunner(template) as handle:
        assert handle.gateway_url.startswith("http://")
        # ``_wait_for_healthz`` inside the runner has already confirmed
        # the endpoint answered 200; assert the handle's shape so a
        # regression that drops a field is caught by this test.
        assert handle.project_name
        assert handle.template_path == template
