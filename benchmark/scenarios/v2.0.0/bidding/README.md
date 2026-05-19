# MARBLE Bidding Experiment Runs

This folder contains the 12 base MARBLE bidding bundles for the v2.0.0 store:
6 `CM-C` competitive-market tasks and 6 `CU-C` cross-user tasks.

The committed manifest has 60 bidding rows: 12 base tasks times 5 total modes.
The five modes are:

- `no_attacker`
- `collaboration`
- `security`
- `privacy`
- `governance`

There are four attacker axes plus the no-attacker control. If a fifth attacker
axis is added later, it must first be added to the v2.0.0 manifest and to the
runtime stress-recipe registry.

## Prerequisites

Run commands from the repository root.

```bash
test -x .venv/bin/python
test -f benchmark/scenarios/v2.0.0/manifest.json
docker compose version
```

Load credentials before live model runs. If your shell already exports the
needed variables, this step can be skipped.

```bash
set -a
source .env
set +a
```

The Docker executor materializes each row under the chosen output directory at:

```text
<out-dir>/variants/<base_id>__<attack_mode>/
```

Each variant writes a transcript and scorecard under:

```text
<variant-dir>/run/simulation_report.json
<variant-dir>/run/run_scorecard.json
```

## Check The Bidding Slice

Confirm that the manifest still has the expected 60 bidding rows:

```bash
jq '[.rows[] | select(.family_id == "marble_bidding")] | length' \
  benchmark/scenarios/v2.0.0/manifest.json
```

Check the mode distribution:

```bash
jq -r '.rows[] | select(.family_id == "marble_bidding") | .attack_mode' \
  benchmark/scenarios/v2.0.0/manifest.json | sort | uniq -c
```

Expected output is 12 rows for each of `no_attacker`, `collaboration`,
`security`, `privacy`, and `governance`.

## Smoke A Single Row

Use one row before launching a full sweep. This command uses the same
driver-orchestrated Docker substrate as the full benchmark.

```bash
RUN_ID=bidding_smoke_no_attacker_$(date +%Y%m%d_%H%M%S)

COMPOSE_BAKE=true .venv/bin/python scripts/run_phase5_pilot.py run-batch \
  --manifest benchmark/scenarios/v2.0.0/manifest.json \
  --base-dir benchmark/scenarios/v2.0.0 \
  --store benchmark/scenarios/v2.0.0 \
  --out-dir benchmark/phase5/pilot/${RUN_ID} \
  --batch 2 \
  --executor docker \
  --mode full \
  --filter family=marble_bidding,mode=no_attacker \
  --limit 1 \
  --agent-model gpt-4.1-mini \
  --max-turns 36 \
  --max-workers 1
```

`--batch 2` is used because it selects main-stratum rows. The `--filter`
narrows the run to bidding rows, and `--limit 1` keeps the smoke run cheap.

## Run The 12-Row No-Attacker Baseline

```bash
RUN_ID=bidding_12_no_attacker_$(date +%Y%m%d_%H%M%S)

COMPOSE_BAKE=true .venv/bin/python scripts/run_phase5_pilot.py run-batch \
  --manifest benchmark/scenarios/v2.0.0/manifest.json \
  --base-dir benchmark/scenarios/v2.0.0 \
  --store benchmark/scenarios/v2.0.0 \
  --out-dir benchmark/phase5/pilot/${RUN_ID} \
  --batch 2 \
  --executor docker \
  --mode full \
  --filter family=marble_bidding,mode=no_attacker \
  --agent-model gpt-4.1-mini \
  --max-turns 36 \
  --max-workers 1
```

The output JSONL is:

```text
benchmark/phase5/pilot/<RUN_ID>/BATCH_02_standard_RESULTS.jsonl
```

Summarize the no-attacker task-success count:

```bash
jq -s '{
  rows: length,
  task_success_true: ([.[] | select(.task_success == true)] | length),
  task_success_false: ([.[] | select(.task_success == false)] | length),
  task_success_null: ([.[] | select(.task_success == null)] | length),
  turn_caps: ([.[] | select(.hit_turn_cap == true)] | length)
}' benchmark/phase5/pilot/${RUN_ID}/BATCH_02_standard_RESULTS.jsonl
```

Do not treat `task_success=false` as an infrastructure failure by itself. A
useful bidding baseline is expected to be scoreable but non-perfect. Rows with
`task_success=null` or missing scorecards are the rows that need runtime
inspection.

## Run One Attack Mode

Use this pattern to rerun one attacker axis across all 12 base tasks:

```bash
MODE=security
RUN_ID=bidding_12_${MODE}_$(date +%Y%m%d_%H%M%S)

COMPOSE_BAKE=true .venv/bin/python scripts/run_phase5_pilot.py run-batch \
  --manifest benchmark/scenarios/v2.0.0/manifest.json \
  --base-dir benchmark/scenarios/v2.0.0 \
  --store benchmark/scenarios/v2.0.0 \
  --out-dir benchmark/phase5/pilot/${RUN_ID} \
  --batch 2 \
  --executor docker \
  --mode full \
  --filter family=marble_bidding,mode=${MODE} \
  --agent-model gpt-4.1-mini \
  --max-turns 36 \
  --max-workers 1
```

Set `MODE` to one of `collaboration`, `security`, `privacy`, or `governance`.

To target a single base task, add the base id to the filter:

```bash
--filter family=marble_bidding,mode=governance,base_id=CU-C-marble_bidding__t4
```

## Run The Full 60-Row Sweep

This runs no-attacker plus all four attacker axes:

```bash
RUN_ID=bidding_12x5_sweep_$(date +%Y%m%d_%H%M%S)

COMPOSE_BAKE=true .venv/bin/python scripts/run_phase5_pilot.py run-batch \
  --manifest benchmark/scenarios/v2.0.0/manifest.json \
  --base-dir benchmark/scenarios/v2.0.0 \
  --store benchmark/scenarios/v2.0.0 \
  --out-dir benchmark/phase5/pilot/${RUN_ID} \
  --batch 2 \
  --executor docker \
  --mode full \
  --filter family=marble_bidding \
  --agent-model gpt-4.1-mini \
  --max-turns 36 \
  --max-workers 1
```

After the run, keep the raw JSONL in the run directory. If a downstream script
expects the bidding-specific filename, make a copy:

```bash
cp benchmark/phase5/pilot/${RUN_ID}/BATCH_02_standard_RESULTS.jsonl \
  benchmark/phase5/pilot/${RUN_ID}/BIDDING_12X5_RESULTS.jsonl
```

Summarize raw task success by mode:

```bash
jq -s '
  group_by(.attack_mode)
  | map({
      mode: .[0].attack_mode,
      rows: length,
      task_success_true: ([.[] | select(.task_success == true)] | length),
      task_success_false: ([.[] | select(.task_success == false)] | length),
      task_success_null: ([.[] | select(.task_success == null)] | length),
      turn_caps: ([.[] | select(.hit_turn_cap == true)] | length)
    })
' benchmark/phase5/pilot/${RUN_ID}/BATCH_02_standard_RESULTS.jsonl
```

## Run Bidding LLM-ASR

Headline bidding ASR must come from the bidding-specific LLM judge. The
deterministic attack-success fields in raw rows are diagnostics only.

```bash
.venv/bin/python -m clawsocialarena.eval.bidding_asr_judge \
  --batch-results benchmark/phase5/pilot/${RUN_ID}/BATCH_02_standard_RESULTS.jsonl \
  --out benchmark/phase5/pilot/${RUN_ID}/BIDDING_LLM_ASR_GPT52.jsonl \
  --base-dir . \
  --judge-model gpt-5.2 \
  --max-workers 4
```

Summarize judged ASR by primary attack mode:

```bash
jq -s '
  [ .[] | select(.attack_mode != "no_attacker") ]
  | group_by(.attack_mode)
  | map({
      mode: .[0].attack_mode,
      rows: length,
      llm_asr_true: ([.[] | select(.llm_judge_bidding_asr.attack_success_aggregate == true)] | length),
      llm_asr_false: ([.[] | select(.llm_judge_bidding_asr.attack_success_aggregate == false)] | length),
      judge_errors: ([.[] | select(.llm_judge_bidding_asr.error != null)] | length)
    })
' benchmark/phase5/pilot/${RUN_ID}/BIDDING_LLM_ASR_GPT52.jsonl
```

## Change The Simulation Model

The simulation model is controlled by `--agent-model`. For reproducibility,
always pass it explicitly.

The model used in the current bidding sweeps was:

```bash
--agent-model gpt-4.1-mini
```

To test another model, replace only that value:

```bash
--agent-model gpt-4.1
```

or:

```bash
--agent-model gpt-5.2
```

The ASR judge model is separate and is controlled by `--judge-model` in
`clawsocialarena.eval.bidding_asr_judge`. Changing `--agent-model` changes the
agents that perform the bidding task. Changing `--judge-model` changes only the
post-run ASR evaluation.

The Docker executor reads already materialized v2.0.0 bundles from
`benchmark/scenarios/v2.0.0`; it does not need a naturalization model for these
runs.

## Turn Budgets

`--max-turns` patches the `max_turns` field in the materialized variant before
the Docker run starts. Use `--max-turns 36` for cap-36 comparability runs.

The committed bidding bundles also carry scenario-local budgets. If you are
reproducing a prior calibration run that relied on scenario-local budgets, check
the task reports under `docs/phase_5/scenarios/bidding/` and keep the chosen
turn policy fixed across the rows you compare.
