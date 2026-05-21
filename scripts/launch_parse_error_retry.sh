#!/usr/bin/env bash
# Launch the 4-scenario parse-error retry against Opus 4.7 in detached screens.
#
# Reads <run_dir>/retry_index.json (produced by enumerating parse-error rows
# from the original RESULTS.jsonl files) and invokes
# scripts/retry_parse_error_rows.py for each scenario in its own screen.
#
# Usage:
#   bash scripts/launch_parse_error_retry.sh [<run_dir>]
#
# Defaults to bedrock_sweep_20260520_093504 if no run_dir is given.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

RUN_DIR="${1:-benchmark/phase5/pilot/bedrock_sweep_20260520_093504}"
AGENT_MODEL="${BEDROCK_OPUS_47_ID:-global.anthropic.claude-opus-4-7}"
PY=".venv/bin/python"

test -f "$RUN_DIR/retry_index.json" || {
  echo "missing $RUN_DIR/retry_index.json (run the enumerator first)"
  exit 1
}
test -x "$PY" || { echo "missing $PY"; exit 1; }

launch() {
  local session="$1" scenario="$2"
  local out_dir="$RUN_DIR/${scenario}_retry"

  if screen -ls | grep -qE "\\.${session}[[:space:]]"; then
    echo "skip: session $session already exists"
    return 0
  fi

  mkdir -p "$out_dir"
  local body
  body=$(cat <<EOF
cd "$REPO_ROOT"
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
echo "[\$(date -Is)] session=$session scenario=$scenario out=$out_dir"
PYTHONPATH=. $PY scripts/retry_parse_error_rows.py \\
  --run-dir "$RUN_DIR" \\
  --scenario "$scenario" \\
  --agent-model "$AGENT_MODEL" \\
  >>"$out_dir/run.log" 2>&1
status=\$?
echo "[\$(date -Is)] exit_status=\$status"
echo "(detach with Ctrl-A d; reattach with: screen -r $session)"
exec bash
EOF
)
  screen -dmS "$session" bash -lc "$body"
  echo "launched: $session -> $out_dir/run.log"
}

launch csa_bargaining_opus47_retry  bargaining_opus47
launch csa_bidding_opus47_retry     bidding_opus47
launch csa_swebench_opus47_retry    swebench_workspace_opus47
launch csa_travel_opus47_retry      travel_opus47

echo
echo "Run dir:  $RUN_DIR"
echo "Sessions: screen -ls | grep _retry"
