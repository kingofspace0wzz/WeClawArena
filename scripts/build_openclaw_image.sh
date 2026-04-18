#!/usr/bin/env bash
# Build the ClawSocialArena OpenClaw-with-plugin Docker image and run a
# `--version` smoke test.
#
# Invoked by:
#   * A14 E2E harness (which consumes the built image to run a full
#     arena episode against a real OpenClaw agent).
#   * CI jobs that want to confirm the image still builds and the CLI is
#     reachable after a plugin change.
#
# The first positional argument overrides the image tag. The build
# context is the worktree root so the Dockerfile can reach
# `gateway_plugin/`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

IMAGE="${1:-clawsocialarena/openclaw-with-plugin:dev}"
DOCKERFILE="${REPO_ROOT}/docker/openclaw-with-plugin.Dockerfile"

if ! command -v docker >/dev/null 2>&1; then
  echo "build_openclaw_image.sh: docker is not installed or not on PATH." >&2
  exit 127
fi

echo "==> Building ${IMAGE}"
docker build \
  -f "${DOCKERFILE}" \
  -t "${IMAGE}" \
  "${REPO_ROOT}"

echo "==> Smoke: openclaw --version"
docker run --rm "${IMAGE}" --version
