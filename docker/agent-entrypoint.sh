#!/usr/bin/env sh
#
# ClawSocialArena OpenClaw agent entrypoint.
#
# Started by the scenario-bundle `docker-compose.yml`. The script waits
# for the arena gateway's `/healthz` to respond, then hands control to
# the OpenClaw CLI with the `clawsocial` channel active so the in-process
# plugin can register against the gateway over HTTP.
#
# Two env vars are required (compose sets both):
#   CLAWSOCIAL_AGENT_ID   -- scenario-local agent id
#   CLAWSOCIAL_GATEWAY_URL -- e.g., `http://gateway:8080`
#
# Persona + tool files are mounted read-only by the compose template:
#   /workspace/persona.system.md
#   /workspace/persona.tools.json
# MCP configs are mounted under `/workspace/mcp/`.
#
# NOTE(Phase F): the exact `openclaw agent` flag surface below matches the
# plugin's intended channel API (`--channel clawsocial`,
# `--channel-config gatewayUrl=...,agentId=...`), but the real OpenClaw
# CLI verbs/flags may differ. Phase F will reconcile the exact invocation
# once the plugin's public CLI wiring lands; the shape (wait, then start
# the channel with gatewayUrl + agentId) is load-bearing.
set -eu

: "${CLAWSOCIAL_AGENT_ID:?agent id not set}"
: "${CLAWSOCIAL_GATEWAY_URL:?gateway url not set}"

# Wait for the gateway's /healthz before launching the agent. Compose's
# `depends_on.condition: service_healthy` already blocks on the gateway's
# own HEALTHCHECK, but this guard is defense in depth for setups that
# point at an external gateway.
python - <<'PY' || { echo "gateway not ready" >&2; exit 1; }
import os
import sys
import time
import urllib.request

url = os.environ["CLAWSOCIAL_GATEWAY_URL"].rstrip("/") + "/healthz"
deadline = time.time() + 60
while time.time() < deadline:
    try:
        urllib.request.urlopen(url, timeout=2)
        sys.exit(0)
    except Exception:
        time.sleep(1)
sys.exit(1)
PY

# Hand off to the OpenClaw CLI. `exec` replaces the shell so the
# container's PID 1 is the agent process and signals propagate cleanly.
exec openclaw agent \
    --channel clawsocial \
    --channel-config "gatewayUrl=${CLAWSOCIAL_GATEWAY_URL},agentId=${CLAWSOCIAL_AGENT_ID}" \
    --persona /workspace/persona.system.md \
    --tools /workspace/persona.tools.json
