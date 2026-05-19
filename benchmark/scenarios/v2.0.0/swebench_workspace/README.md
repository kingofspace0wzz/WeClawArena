# SWE-bench Workspace Experiments

This directory contains the published `swebench_workspace` base bundles for v2.0.0. The release manifest lives at `benchmark/scenarios/v2.0.0/manifest.json`.

The current sweep has five modes total:

| Mode | Meaning |
|---|---|
| `no_attacker` | baseline run with no attack overlay |
| `security` | workspace integrity attack |
| `privacy` | private workspace information-flow attack |
| `governance` | authority, identity, and approval attack |
| `collaboration` | poisoned handoff or review-state attack |

Attack variants are materialized at runtime. They are not stored as copied bundle directories under this dataset path.

## Prerequisites

Run commands from the repository root.

Required local services and credentials:

- Docker must be running.
- The project virtual environment should be available at `.venv`.
- Provider credentials should be loaded from `.env` before paid simulation or judge runs.

```bash
set -a
source .env
set +a
```

Optional but recommended for Docker builds:

```bash
export COMPOSE_BAKE=true
```

## Full Five-Mode Sweep

This command runs all `swebench_workspace` rows in the published manifest: 50 no-attacker rows and 200 attack rows.

```bash
OUT=benchmark/phase5/pilot/swebench_workspace_cap90_50base_5mode_$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUT"

.venv/bin/python scripts/run_phase5_pilot.py run-batch \
  --manifest benchmark/scenarios/v2.0.0/manifest.json \
  --base-dir benchmark/scenarios/v2.0.0 \
  --store benchmark/scenarios/v2.0.0 \
  --out-dir "$OUT" \
  --batch 2 \
  --executor docker \
  --filter family=swebench_workspace \
  --max-turns 90 \
  --max-workers 4 \
  --agent-model gpt-4.1-mini \
  > "$OUT/run.log" 2>&1
```

Notes:

- `--batch 2` is the standard main-row batch. The family filter narrows it to the 250 `swebench_workspace` rows.
- `--max-turns 90` is the current cap-normalized reporting budget.
- `--max-workers 4` was used for the cap-90 calibration run. Use `--max-workers 1` if Docker image builds or local machine pressure cause instability.
- `--agent-model` controls the simulated agents. The earlier workspace runs used `gpt-4.1-mini`; pass another model id here for cross-model experiments.
- `--naturalization-model` is not relevant for this published-store Docker rerun because the bundles have already been materialized.

The main outputs are:

| File | Purpose |
|---|---|
| `BATCH_02_standard_RESULTS.jsonl` | one row per simulation |
| `BATCH_02_standard_REPORT.json` | aggregate runner report |
| `run.log` | stdout and stderr from the batch command |
| `variants/<variant_id>/run/` | per-row scorecards, reports, and traces |

## Run One Mode

For a smaller run, add a `mode` filter.

No-attacker only:

```bash
OUT=benchmark/phase5/pilot/swebench_workspace_no_attacker_$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUT"

.venv/bin/python scripts/run_phase5_pilot.py run-batch \
  --manifest benchmark/scenarios/v2.0.0/manifest.json \
  --base-dir benchmark/scenarios/v2.0.0 \
  --store benchmark/scenarios/v2.0.0 \
  --out-dir "$OUT" \
  --batch 2 \
  --executor docker \
  --filter family=swebench_workspace,mode=no_attacker \
  --max-turns 90 \
  --max-workers 4 \
  --agent-model gpt-4.1-mini \
  > "$OUT/run.log" 2>&1
```

One attack mode:

```bash
MODE=security
OUT=benchmark/phase5/pilot/swebench_workspace_${MODE}_$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUT"

.venv/bin/python scripts/run_phase5_pilot.py run-batch \
  --manifest benchmark/scenarios/v2.0.0/manifest.json \
  --base-dir benchmark/scenarios/v2.0.0 \
  --store benchmark/scenarios/v2.0.0 \
  --out-dir "$OUT" \
  --batch 2 \
  --executor docker \
  --filter family=swebench_workspace,mode="$MODE" \
  --max-turns 90 \
  --max-workers 4 \
  --agent-model gpt-4.1-mini \
  > "$OUT/run.log" 2>&1
```

Valid attack modes are `security`, `privacy`, `governance`, and `collaboration`.

## Change The Simulation Model

The simulated-agent model is controlled by `--agent-model`.

Examples:

```bash
--agent-model gpt-4.1-mini
--agent-model gpt-5.2
--agent-model gpt-5-mini
```

Use a separate output directory for each model so artifacts do not overwrite each other:

```bash
MODEL=gpt-4.1-mini
OUT=benchmark/phase5/pilot/swebench_workspace_${MODEL}_cap90_$(date +%Y%m%d_%H%M%S)
```

The LLM-ASR judge model is separate from the simulation model and is set with `--judge-model` in the post-processing step below.

## Split Baseline And Attack Rows

After a full sweep, split the runner JSONL into baseline and attack rows:

```bash
python - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
src = out / "BATCH_02_standard_RESULTS.jsonl"
baseline = out / "BATCH_02_standard_BASELINE_ROWS.jsonl"
attack = out / "BATCH_02_standard_ATTACK_ROWS.jsonl"

with src.open("r", encoding="utf-8") as in_f, \
     baseline.open("w", encoding="utf-8") as base_f, \
     attack.open("w", encoding="utf-8") as attack_f:
    for line in in_f:
        if not line.strip():
            continue
        row = json.loads(line)
        target = base_f if row.get("attack_mode") == "no_attacker" else attack_f
        target.write(json.dumps(row, sort_keys=True) + "\n")

print(f"wrote {baseline}")
print(f"wrote {attack}")
PY
```

Expected row counts for a full current sweep:

```bash
wc -l "$OUT"/BATCH_02_standard_RESULTS.jsonl \
      "$OUT"/BATCH_02_standard_BASELINE_ROWS.jsonl \
      "$OUT"/BATCH_02_standard_ATTACK_ROWS.jsonl
```

The expected counts are 250, 50, and 200.

## Run The Workspace LLM-ASR Judge

Run the judge on attack rows:

```bash
.venv/bin/python -m clawsocialarena.eval.workspace_asr_judge \
  --input-jsonl "$OUT/BATCH_02_standard_ATTACK_ROWS.jsonl" \
  --output-jsonl "$OUT/BATCH_02_standard_ATTACK_ROWS.workspace_llm_asr.jsonl" \
  --run-dir "$OUT" \
  --baseline-jsonl "$OUT/BATCH_02_standard_BASELINE_ROWS.jsonl" \
  --judge-model gpt-5.2 \
  --max-workers 4
```

Run the same judge on no-attacker controls to check false positives:

```bash
.venv/bin/python -m clawsocialarena.eval.workspace_asr_judge \
  --input-jsonl "$OUT/BATCH_02_standard_BASELINE_ROWS.jsonl" \
  --output-jsonl "$OUT/BATCH_02_standard_BASELINE_ROWS.workspace_llm_asr.jsonl" \
  --run-dir "$OUT" \
  --baseline-jsonl "$OUT/BATCH_02_standard_BASELINE_ROWS.jsonl" \
  --judge-model gpt-5.2 \
  --max-workers 4
```

Generate the Markdown LLM-ASR report:

```bash
.venv/bin/python scripts/report_workspace_stress_calibration.py \
  --input-jsonl "$OUT/BATCH_02_standard_ATTACK_ROWS.workspace_llm_asr.jsonl" \
  --output-md "$OUT/BATCH_02_standard_WORKSPACE_LLM_ASR_REPORT.md"
```

## Interpreting Results

Report task success and LLM-ASR as separate axes:

- Task success is the main utility metric.
- LLM-ASR is the attack-success metric for attack rows.
- No-attacker judge positives should be reported as false positives.
- Deterministic ASR is not the main `swebench_workspace` attack metric.

For the current cap-90 calibration, see `docs/phase_5/scenarios/swebench_workspace/summary.md` and `docs/superpowers/specs/swebench_workspace/`.

## Cleanup After Interrupted Runs

If a Docker run is interrupted, check for leftover workspace containers or networks:

```bash
docker ps -a --format '{{.Names}}' | rg '^csa-swebench_workspace'
docker network ls --format '{{.Name}}' | rg '^csa-swebench_workspace'
```

Remove only resources that belong to the interrupted run.
