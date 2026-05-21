#!/usr/bin/env bash
# Launch the v2.0.0 5-mode sweep over 4 scenarios x 2 Bedrock Claude models in
# 8 detached GNU screen sessions (1 scenario x model per screen).
#
# Scenarios (5 modes each: no_attacker, collaboration, security, privacy, governance):
#   - bargaining        (24 bases x 5 modes = 120 rows)
#   - bidding           (12 bases x 5 modes =  60 rows)
#   - swebench_workspace(50 bases x 5 modes = 250 rows)
#   - travel            (20 bases x 5 modes = 100 rows)
#
# Models (via Bedrock):
#   - Claude Sonnet 4.6
#   - Claude Opus 4.7
#
# Each scenario+model lands in its own screen so the 4 scenarios run in parallel
# and, within each scenario, the two models also run in parallel: 8 screens total.
#
# Usage:
#   bash scripts/launch_bedrock_v2_0_0_sweep.sh [--dry-run]
#
# Then attach to any session:
#   screen -ls
#   screen -r csa_bargaining_sonnet46
#
# Detach with Ctrl-A d.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Bedrock model identifiers as understood by the runtime's `--agent-model`
# argument. Override via env if your provider plugin expects a different form
# (for example a LiteLLM-style prefix like `bedrock/<id>` or an inference
# profile ARN). The values below assume US cross-region inference profile IDs.
: "${BEDROCK_SONNET_46_ID:=global.anthropic.claude-sonnet-4-6}"
: "${BEDROCK_OPUS_47_ID:=global.anthropic.claude-opus-4-7}"

# Modes for the bargaining runner. The phase5 pilot runner pulls modes from the
# manifest automatically when filtered by family, so it does not need an
# explicit --modes flag.
MODES="no_attacker,collaboration,security,privacy,governance"

# Output root. One subdirectory per (scenario, model) sweep. Override the
# default ``bedrock_sweep_<timestamp>`` root by exporting OUT_ROOT, e.g. to
# land a partial relaunch in the same dir as an earlier sweep.
RUN_STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_ROOT="${OUT_ROOT:-benchmark/phase5/pilot/bedrock_sweep_${RUN_STAMP}}"

# Per-scenario turn caps and worker counts (matched to each scenario README).
BARGAINING_MAX_TURNS=36
BIDDING_MAX_TURNS=36
SWEBENCH_MAX_TURNS=90
TRAVEL_MAX_TURNS=36

BIDDING_MAX_WORKERS=1
SWEBENCH_MAX_WORKERS=4
TRAVEL_MAX_WORKERS=4

PY=".venv/bin/python"
MANIFEST="benchmark/scenarios/v2.0.0/manifest.json"
STORE="benchmark/scenarios/v2.0.0"

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

# ---------------------------------------------------------------------------
# Pre-flight (skipped during --dry-run so plan inspection works without venv)
# ---------------------------------------------------------------------------

if [[ "$DRY_RUN" -eq 0 ]]; then
  command -v screen >/dev/null || { echo "screen not installed"; exit 1; }
  test -x "$PY" || { echo "missing $PY -- create the project venv first"; exit 1; }
  test -f "$MANIFEST" || { echo "missing $MANIFEST"; exit 1; }
  test -f ".env" || echo "warn: no .env at repo root; paid runs will fail without provider credentials"
  mkdir -p "$OUT_ROOT"
fi

# ---------------------------------------------------------------------------
# Session launcher
# ---------------------------------------------------------------------------
#
# Each session sources .env (to pick up AWS/Bedrock and LLM credentials), cds
# into the repo, then runs one sweep command with PYTHONPATH=. and all stdout
# and stderr captured to <out>/run.log. After the command exits, the shell
# stays attached so you can inspect the tail before closing the session.

launch() {
  local session="$1"
  local out_dir="$2"
  local cmd="$3"

  mkdir -p "$out_dir"

  local body
  body=$(cat <<EOF
cd "$REPO_ROOT"
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
mkdir -p "$out_dir"
echo "[\$(date -Is)] session=$session out=$out_dir"
echo "[\$(date -Is)] cmd: $cmd"
PYTHONPATH=. $cmd >>"$out_dir/run.log" 2>&1
status=\$?
echo "[\$(date -Is)] exit_status=\$status"
echo "(detach with Ctrl-A d; reattach with: screen -r $session)"
exec bash
EOF
)

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "----- $session -----"
    echo "out_dir: $out_dir"
    echo "cmd:     $cmd"
    return 0
  fi

  if screen -ls | grep -qE "\\.${session}[[:space:]]"; then
    echo "skip: session $session already exists (screen -r $session to attach)"
    return 0
  fi

  screen -dmS "$session" bash -lc "$body"
  echo "launched: $session  ->  $out_dir/run.log"
}

# ---------------------------------------------------------------------------
# Per-scenario command builders
# ---------------------------------------------------------------------------

bargaining_cmd() {
  local model_id="$1" out="$2"
  printf '%s' "\
$PY scripts/run_bargaining_stress_calibration.py \
--store $STORE \
--out-dir \"$out\" \
--agent-model \"$model_id\" \
--max-turns $BARGAINING_MAX_TURNS \
--modes $MODES \
--audit-condition passive \
--simulation-attempts 1"
}

bidding_cmd() {
  local model_id="$1" out="$2"
  printf '%s' "\
COMPOSE_BAKE=true $PY scripts/run_phase5_pilot.py run-batch \
--manifest $MANIFEST \
--base-dir $STORE \
--store $STORE \
--out-dir \"$out\" \
--batch 2 \
--executor docker \
--mode full \
--filter family=marble_bidding \
--agent-model \"$model_id\" \
--max-turns $BIDDING_MAX_TURNS \
--max-workers $BIDDING_MAX_WORKERS"
}

swebench_cmd() {
  local model_id="$1" out="$2"
  printf '%s' "\
COMPOSE_BAKE=true $PY scripts/run_phase5_pilot.py run-batch \
--manifest $MANIFEST \
--base-dir $STORE \
--store $STORE \
--out-dir \"$out\" \
--batch 2 \
--executor docker \
--mode full \
--filter family=swebench_workspace \
--agent-model \"$model_id\" \
--max-turns $SWEBENCH_MAX_TURNS \
--max-workers $SWEBENCH_MAX_WORKERS"
}

travel_cmd() {
  local model_id="$1" out="$2"
  printf '%s' "\
$PY scripts/run_phase5_pilot.py run-batch \
--manifest $MANIFEST \
--base-dir $STORE \
--store $STORE \
--out-dir \"$out\" \
--batch 2 \
--executor docker \
--mode full \
--filter family=travel \
--agent-model \"$model_id\" \
--max-turns $TRAVEL_MAX_TURNS \
--max-workers $TRAVEL_MAX_WORKERS"
}

# ---------------------------------------------------------------------------
# Launch the 8 sweeps
# ---------------------------------------------------------------------------

declare -A MODELS=(
  [sonnet46]="$BEDROCK_SONNET_46_ID"
  [opus47]="$BEDROCK_OPUS_47_ID"
)

for tag in sonnet46 opus47; do
  model_id="${MODELS[$tag]}"

  out_b="$OUT_ROOT/bargaining_${tag}"
  launch "csa_bargaining_${tag}" "$out_b" "$(bargaining_cmd "$model_id" "$out_b")"

  out_bid="$OUT_ROOT/bidding_${tag}"
  launch "csa_bidding_${tag}" "$out_bid" "$(bidding_cmd "$model_id" "$out_bid")"

  out_swe="$OUT_ROOT/swebench_workspace_${tag}"
  launch "csa_swebench_${tag}" "$out_swe" "$(swebench_cmd "$model_id" "$out_swe")"

  out_t="$OUT_ROOT/travel_${tag}"
  launch "csa_travel_${tag}" "$out_t" "$(travel_cmd "$model_id" "$out_t")"
done

echo
echo "Output root: $OUT_ROOT"
echo "Sessions:    screen -ls | grep csa_"
echo "Attach with: screen -r <session>   (detach: Ctrl-A d)"
