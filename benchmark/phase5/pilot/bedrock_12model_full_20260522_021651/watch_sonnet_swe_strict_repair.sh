#!/usr/bin/env bash
set -euo pipefail

REPO="/tmp/WeClawArena_repair_clean_20260525"
ROOT="$REPO/benchmark/phase5/pilot/bedrock_12model_full_20260522_021651"
STRICT="$ROOT/_swebench_harness_strict/sonnet_45_id"
LOG="$ROOT/_sonnet_swe_strict_repair_watch.log"

rows() {
  local path="$1"
  if [ -f "$path" ]; then
    awk 'NF {n++} END {print n+0}' "$path"
  else
    echo 0
  fi
}

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*" | tee -a "$LOG"
}

cd "$REPO"
log "strict repair watcher start"

while screen -ls | grep -q 'csa_sonnet_swe_strict_repair'; do
  "$REPO/.venv/bin/python" "$ROOT/update_live_results.py" --root "$ROOT" >/dev/null 2>&1 || true
  log "running strict_rows=$(rows "$STRICT/strict_accumulator.jsonl") report_exists=$([ -f "$STRICT/strict_report.json" ] && echo 1 || echo 0)"
  sleep 300
done

"$REPO/.venv/bin/python" "$ROOT/update_live_results.py" --root "$ROOT" >/dev/null 2>&1 || true
log "strict screen exited strict_rows=$(rows "$STRICT/strict_accumulator.jsonl")"

if [ "$(rows "$STRICT/strict_accumulator.jsonl")" -ne 250 ]; then
  log "not committing: strict accumulator is not 250 rows"
  exit 1
fi

if grep -R -q -E 'ExpiredTokenException|security token included in the request is expired|ValidationException|provided model identifier is invalid' "$STRICT" "$ROOT/sonnet_45_id/swebench_workspace/BATCH_02_standard_RESULTS.jsonl"; then
  log "not committing: token/model validation marker found"
  exit 1
fi

git add -u
git add -f "$REPO/scripts/export_swebench_workspace_predictions.py" "$ROOT/watch_sonnet_swe_strict_repair.sh"

if git diff --cached --quiet; then
  log "nothing to commit"
  exit 0
fi

git commit -m "Repair Sonnet SWE strict evaluation"
git push origin HEAD:main
log "committed and pushed $(git rev-parse --short HEAD)"
