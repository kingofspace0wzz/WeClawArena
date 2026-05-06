# syntax=docker/dockerfile:1.6
#
# ClawSocialArena gateway runtime image.
#
# The gateway is the in-process MCP + HTTP side-channel host that
# arena scenarios talk to over a private Docker network. It exposes
# `/healthz`, `/send`, `/recv`, `/tool_call`, `/tool_observation_return`,
# `/memory_write`, `/llm_call`, and `/mcp/<tool>` on TCP 8080.
#
# Build context is the worktree root so `clawsocialarena/` and
# `pyproject.toml` are reachable in a single pass. See
# `docker/compose-templates/minimal.yml` for a sample invocation and
# the A14 E2E harness for the canonical end-to-end smoke.

FROM python:3.11-slim AS base
WORKDIR /app

# `build-essential` is kept for wheels that still need a local compiler
# (e.g., optional scientific deps pulled in transitively). Everything
# else stays in a single `apt-get update` + `install` + cleanup layer so
# the image does not ship the apt cache.
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
 && rm -rf /var/lib/apt/lists/*

# Install deps first (ahead of the source copy) so a pure code edit does
# not invalidate the heavy pip layer. The version floors mirror the ones
# declared in `pyproject.toml` to keep the runtime honest.
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
      "aiohttp>=3.9" \
      "pydantic>=2.12" \
      "numpy>=1.26" \
      "networkx>=3.2" \
      "pandas>=2.2" \
      "matplotlib>=3.8" \
      "seaborn>=0.13" \
      "openai>=1.14" \
      "boto3>=1.34" \
      "pyyaml>=6.0" \
      "httpx>=0.27"

# Now bring in the gateway source and install the package itself.
# `--no-deps` is safe here because the previous layer has already
# resolved the runtime dependencies.
COPY clawsocialarena ./clawsocialarena
RUN pip install --no-cache-dir -e . --no-deps

EXPOSE 8080

# CLI defaults keep the image runnable without any extra flags
# (`--condition baseline` means no DB path is required; see
# `clawsocialarena/gateway/server.py`).
ENTRYPOINT ["python", "-m", "clawsocialarena.gateway.server"]
CMD ["--host", "0.0.0.0", "--port", "8080", "--scenario-id", "gateway-default", "--condition", "baseline"]

# Healthcheck hits the `/healthz` route built in Task A1. The interval
# is short so compose's `depends_on: service_healthy` gates settle
# quickly during E2E runs.
HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
  CMD python -c "import urllib.request, sys; \
sys.exit(0 if urllib.request.urlopen('http://localhost:8080/healthz').status == 200 else 1)"
