"""End-to-end smoke test: one OpenClaw container sends a message, gateway logs it.

Skipped on hosts without Docker. A14 writes the scaffold; it will be
exercised in Phase G once Docker and a real OpenClaw plugin install chain
are available.

The test drives alice's OpenClaw container via ``docker compose exec`` to
issue a single outbound send through the arena plugin, then polls the
gateway's ``/recv`` endpoint for bob's inbox to confirm the gateway saw
exactly one outbound message with the expected sender and content. Under
the in-process gateway, a successful ``/send`` enqueues the payload into
``bob``'s asyncio queue and appends one ``outbound_message`` record to the
action log; the ``/recv`` assertion is the closest user-facing probe that
does not require reaching into container-internal state.

The OpenClaw CLI currently installs and loads external channel plugins,
but ``openclaw message send`` still validates channels against a narrower
delivery allowlist. The smoke therefore imports the installed
ClawSocialArena plugin inside the OpenClaw image and calls its outbound
adapter directly. This keeps the E2E focused on the arena-owned contract:
the packaged plugin can route an outbound message through the audit
gateway from inside the agent container.
"""
from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from clawsocialarena.gateway.compose_runner import ComposeRunner, docker_available


pytestmark = pytest.mark.skipif(
    not docker_available(), reason="docker not installed on this host"
)


def test_minimal_compose_one_outbound_logged() -> None:
    """Alice sends one message via OpenClaw; gateway records one outbound."""

    # ``parents[2]`` walks from ``tests/e2e/test_minimal_compose.py`` up to
    # the worktree root, matching the sibling ``test_compose_up_down.py``
    # resolution. Keeping it local avoids extending the fixture surface.
    template = (
        Path(__file__).resolve().parents[2]
        / "docker"
        / "compose-templates"
        / "minimal.yml"
    )
    assert template.exists(), f"minimal compose template missing at {template}"

    with ComposeRunner(template) as handle:
        # Have alice send a message to bob via the packaged gateway
        # plugin. ``exec -T`` disables the pseudo-TTY so the command is
        # usable from a non-interactive pytest run.
        subprocess.run(
            [
                "docker", "compose",
                "-f", str(template),
                "-p", handle.project_name,
                "exec", "-T", "alice",
                "node", "--input-type=module", "-e",
                """
const { plugin } = await import('/home/node/.openclaw/extensions/clawsocial/dist/index.js');
await plugin.start({
  agentId: 'alice',
  accountId: 'alice',
  baseUrl: process.env.CLAWSOCIAL_GATEWAY_URL,
  autoStartPolling: false,
});
try {
  const result = await plugin.outbound.sendText({
    accountId: 'alice',
    to: 'bob',
    text: 'hello bob',
  });
  if (result.channel !== 'clawsocial') {
    throw new Error(`unexpected channel ${result.channel}`);
  }
} finally {
  await plugin.stop('alice');
}
""",
            ],
            check=True,
        )

        # Assert the gateway recorded exactly one outbound message with
        # the expected content. In the single-process gateway we probe
        # the in-memory action log indirectly by popping bob's inbox via
        # ``POST /recv``; this is the simplest user-facing assertion that
        # does not require reaching into container-internal state.
        #
        # ``/recv`` is non-blocking: an empty queue yields HTTP 204. We
        # give the plugin a short polling window so a slow outbound
        # delivery (plugin poll-loop latency, network bridge handoff)
        # does not race the assertion. A hard 200 + equality check on
        # the parsed body catches both the "no message delivered" and
        # "wrong content" failure modes.
        deadline = time.monotonic() + 10.0
        body: dict | None = None
        while time.monotonic() < deadline:
            req = urllib.request.Request(
                handle.gateway_url + "/recv",
                data=json.dumps({"recipient_id": "bob"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        body = json.loads(resp.read().decode())
                        break
                    # 204 (empty queue) is expected while the send is in
                    # flight; keep polling until the deadline.
            except urllib.error.HTTPError:
                # Treat a transient HTTP error the same as "not yet" so
                # a gateway restart during the bring-up does not flake.
                pass
            time.sleep(0.25)

        assert body is not None, (
            "gateway /recv did not return a 200 within the polling window; "
            "expected bob's inbox to contain one message from alice"
        )
        assert body == {"sender_id": "alice", "content": "hello bob"}

        # Second /recv must be 204 (empty) so the "exactly one
        # outbound_message" guarantee is asserted end-to-end: any
        # duplicated send or stray retry would leave a second entry in
        # bob's queue.
        req2 = urllib.request.Request(
            handle.gateway_url + "/recv",
            data=json.dumps({"recipient_id": "bob"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req2, timeout=2) as resp2:
            assert resp2.status == 204, (
                f"expected 204 on second /recv (queue drained), got {resp2.status}"
            )
