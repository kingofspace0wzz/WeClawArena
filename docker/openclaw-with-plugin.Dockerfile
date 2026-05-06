# syntax=docker/dockerfile:1.6
#
# ClawSocialArena OpenClaw runtime image.
#
# Stage 1 (`plugin-builder`) turns the TypeScript plugin under
# `gateway_plugin/` into an npm tarball via `pnpm run build` + `npm pack`.
# Stage 2 (`runtime`) is the image the arena actually runs: it installs
# the OpenClaw CLI from the public npm registry and registers the
# preloaded plugin tarball with `openclaw plugins install`.
#
# The image is built with the worktree root as the build context so the
# `gateway_plugin/` directory is reachable without extra copies. See
# `scripts/build_openclaw_image.sh` for the canonical build invocation
# and the `--version` smoke that A14 / CI use to confirm the image is
# functional.

# ---------------------------------------------------------------------------
# Stage 1: build the ClawSocialArena plugin tarball.
# ---------------------------------------------------------------------------
FROM node:24-alpine AS plugin-builder

# `corepack` is shipped with Node.js 24 but is opt-in; enabling it lets
# the stage call `pnpm` directly without a global `npm install -g pnpm`.
RUN corepack enable \
 && corepack prepare pnpm@latest --activate

WORKDIR /src

# Copy the manifest pair first so Docker can cache `pnpm install` across
# source edits. `--frozen-lockfile` matches CI behavior and rejects any
# drift between `package.json` and `pnpm-lock.yaml`.
COPY gateway_plugin/package.json gateway_plugin/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Now bring in the rest of the plugin source and compile + pack.
# `npm pack --pack-destination /out` drops a single
# `clawsocialarena-gateway-plugin-<version>.tgz` into `/out`, which the
# runtime stage picks up by glob.
COPY gateway_plugin/ ./
RUN pnpm run build \
 && mkdir -p /out \
 && npm pack --pack-destination /out

# ---------------------------------------------------------------------------
# Stage 2: runtime image.
# ---------------------------------------------------------------------------
FROM node:24-alpine AS runtime

# Pin OpenClaw to a known major; the plugin's `peerDependencies` entry
# tracks the same version range.
ARG OPENCLAW_VERSION=latest
RUN npm install -g "openclaw@${OPENCLAW_VERSION}"

# OpenClaw's plugin installer and the arena entrypoint both expect
# Python on PATH.
RUN apk add --no-cache python3 py3-pip \
 && ln -sf /usr/bin/python3 /usr/local/bin/python

# OpenClaw stores per-user state under `<home>/.openclaw`; pinning the
# home root gives A14 a stable mount point for cassettes and arena config.
# This must be set before plugin installation so build-time and runtime
# plugin registries are the same registry.
ENV HOME=/home/node
ENV OPENCLAW_HOME=/home/node

# Bring the packed plugin across. The wildcard tolerates the version
# suffix that `npm pack` adds to the filename.
COPY --from=plugin-builder /out/*.tgz /tmp/clawsocial-plugin.tgz

# Register the plugin with the OpenClaw CLI. `openclaw plugins install`
# accepts a local `.tgz` path; we remove the tarball afterward so the
# final image does not ship two copies of the plugin bytes.
RUN openclaw plugins install /tmp/clawsocial-plugin.tgz \
 && rm /tmp/clawsocial-plugin.tgz

WORKDIR /workspace

# The scenario bundle compose file invokes this script as the agent
# container's `command`; it waits for the gateway's `/healthz` and then
# hands off to the OpenClaw CLI with the `clawsocial` channel active.
# Shipping the script in the image keeps the bundle small -- compose
# only has to reference the in-image path.
#
COPY docker/agent-entrypoint.sh /usr/local/bin/agent-entrypoint.sh
RUN chmod +x /usr/local/bin/agent-entrypoint.sh

# The `--version` smoke that `scripts/build_openclaw_image.sh` runs
# after build relies on this entrypoint so `docker run <image> --version`
# reaches the CLI directly. The scenario compose file overrides
# `command` with `agent-entrypoint.sh` to run the full agent loop.
ENTRYPOINT ["openclaw"]
CMD ["--help"]
