# Travel v2.0.0 Bundles

This directory holds the 20 published base bundles for the travel family in the v2.0.0 manifest:

- `CU-D-travel__t0` .. `CU-D-travel__t9` — 10 CU triad bases (traveler + partner_hotel + corp_travel_approver)
- `MG-C-travel__t0` .. `MG-C-travel__t9` — 10 MG group bases (organizer + 3 co_travelers + partner_hotel)

The manifest (`../manifest.json`) carries 100 travel rows: each base × 5 modes (`no_attacker`, `security`, `privacy`, `governance`, `collaboration`). Attack variants are NOT stored as fully copied folders; the runner materializes them at runtime via `clawsocialarena.attacks.runtime_overlay.materialize_runtime_variant` plus the travel mode-local playbook (`clawsocialarena/attacks/stress_recipes/travel_mode_local_playbooks.py`).

For the full design + calibration story see `docs/superpowers/specs/travel/` (data_construction, attack_vector_design, task_success_metrics, llm_attack_success_evaluator) and the per-scenario pages under `docs/phase_5/scenarios/travel/`.

## Bundle Layout

Each `<base_id>/` directory has:

```text
<base_id>/
  scenario.json              # post-naturalization scenario record
  scenario.gt.json           # ground-truth answer + canonical evaluation
  family_pack_context.json   # trip_id, owner ids, target/floor rates, etc.
  phase5_metadata.json       # cell, task index, source seed
  personas/
    <agent_id>.system.md     # per-agent system prompt (with 2026-05-18 guardrails)
    <agent_id>.tools.json    # per-agent allowed-tool list
  resources/
    agents/<owner_id>/files/...      # owned filesystem slice
    agents/<owner_id>/db/personal.sqlite  # owned SQLite state
  mcp/                       # per-tool MCP manifest stubs
```

## Prerequisites

Before running a sweep:

1. **Python deps**: install with `uv` or `pip`. The runner uses `python3 scripts/run_phase5_pilot.py`. Verify with `python3 -m clawsocialarena.eval.travel_asr_judge --help`.
2. **Docker**: the recommended executor is `docker`. The agent runner spins one container per agent per variant inside `csa-<variant_id>-<agent_id>-1`. Verify with `docker ps`.
3. **API key**: copy `.env.example` to `.env` and set `OPENAI_API_KEY=sk-...`. The shell snippets below `source` it before the sweep.
4. **Disk**: plan for `~5-10 GB` of free space under `benchmark/phase5/pilot/<run_name>/variants/` for a 100-variant docker sweep (each variant holds `cassette.jsonl`, `action_log.db`, `run_scorecard.json`, and per-agent compose state).

## Running a Sweep

### Full 100-variant sweep (no_attacker + 4 attack modes × 20 bases)

```bash
RUN_OUT=benchmark/phase5/pilot/travel_full_$(date +%Y%m%d_%H%M)
mkdir -p "$RUN_OUT"
set -a; source .env; set +a

python3 scripts/run_phase5_pilot.py run-batch \
  --manifest benchmark/scenarios/v2.0.0/manifest.json \
  --base-dir benchmark/scenarios/v2.0.0 \
  --store    benchmark/scenarios/v2.0.0 \
  --out-dir  "$RUN_OUT" \
  --batch 2 \
  --executor docker \
  --agent-model gpt-4.1-mini \
  --max-turns 36 \
  --filter 'family=travel' \
  --mode full \
  > "$RUN_OUT/_sweep.log" 2>&1
```

Wall time: roughly 50 minutes on a single Mac with `max_workers` defaulted by the runner (~4-5 parallel variants depending on docker daemon load). The run produces:

```text
<RUN_OUT>/
  BATCH_02_standard_RESULTS.jsonl   # one row per variant
  BATCH_02_standard_REPORT.json     # summary (TSR baseline / attacker, ASR delta-based)
  _sweep.log                        # full stdout/stderr
  variants/
    <variant_id>/
      run/
        cassette.jsonl              # the agent message + tool transcript
        action_log.db               # SQLite of all tool dispatches
        run_scorecard.json          # per-variant predicate scorecard
        simulation_report.json
      personas/, resources/, scenario.json, ...
```

### Smoke first (10 variants, t0 across both cells)

```bash
SMOKE_OUT=benchmark/phase5/pilot/travel_smoke_$(date +%Y%m%d_%H%M)
mkdir -p "$SMOKE_OUT"
set -a; source .env; set +a

python3 scripts/run_phase5_pilot.py run-batch \
  --manifest benchmark/scenarios/v2.0.0/manifest.json \
  --base-dir benchmark/scenarios/v2.0.0 \
  --store    benchmark/scenarios/v2.0.0 \
  --out-dir  "$SMOKE_OUT" \
  --batch 2 \
  --executor docker \
  --agent-model gpt-4.1-mini \
  --max-turns 36 \
  --filter 'family=travel,task=0' \
  --mode full
```

Wall time: ~7-10 minutes. Useful to validate the redesign on the most-broken cells before paying the full sweep bill.

### Single (cell, axis) probe

```bash
python3 scripts/run_phase5_pilot.py run-batch \
  --manifest benchmark/scenarios/v2.0.0/manifest.json \
  --base-dir benchmark/scenarios/v2.0.0 \
  --store    benchmark/scenarios/v2.0.0 \
  --out-dir  benchmark/phase5/pilot/travel_probe_$(date +%Y%m%d_%H%M) \
  --batch 2 --executor docker --agent-model gpt-4.1-mini --max-turns 36 \
  --filter 'family=travel,cell=MG-C-travel,task=0,mode=governance' \
  --mode full
```

The filter accepts comma-separated `key=value` pairs (AND-ed). Valid keys are `family`, `cell`, `task`, `mode`, `base_id`.

## Changing the Model

The per-agent simulation model is passed via `--agent-model`. To switch from `gpt-4.1-mini` to another OpenAI-compatible model:

```bash
# stronger ceiling (use sparingly -- token cost rises with team size)
python3 scripts/run_phase5_pilot.py run-batch ... --agent-model gpt-5.2

# cheaper smoke
python3 scripts/run_phase5_pilot.py run-batch ... --agent-model gpt-4.1-nano

# named override (any OpenAI-compatible chat-completion id works)
python3 scripts/run_phase5_pilot.py run-batch ... --agent-model gpt-4o-mini
```

**Calibration note**: the travel calibration bands in `docs/superpowers/specs/travel/llm_attack_success_evaluator.md` are anchored to `gpt-4.1-mini`. Switching the agent model will shift both TSR and per-axis ASR. The `<50%` TSR target is the calibration goal for `gpt-4.1-mini`; stronger models are expected to land above that.

The judge model is independent. By default it is `gpt-5.2` for the travel ASR judge, set via `--judge-model gpt-5.2`. To swap:

```bash
python3 -m clawsocialarena.eval.travel_asr_judge \
  --batch-results <RUN_OUT>/BATCH_02_standard_RESULTS.jsonl \
  --out           <RUN_OUT>/BATCH_02_standard_RESULTS_llm_judged.jsonl \
  --base-dir      benchmark/scenarios/v2.0.0 \
  --judge-model   gpt-5.2 \
  --max-workers   4
```

The judge runs in `~10-15 min` for a 100-row sweep at `max_workers=4` and costs `~1.05M total tokens` (`~1.0M prompt + ~50k completion`).

## Other Sweep Knobs

| Flag | Default | When to change |
|---|---|---|
| `--max-turns` | 36 | Lower (24-30) to make the family harder; raise (48+) to give the focal more rope on collaboration-attack runs. Below 30 the MG no_attacker baseline drops below 50%. |
| `--max-workers` | runner default (~4) | Drop to 1 when sharing a host with other heavy docker sweeps; raise on a dedicated machine with `>32 GB` RAM. |
| `--mode` | `full` | `naturalization_only` runs the naturalization pipeline without the agent loop; not useful for travel since travel ships with English translations and `naturalization_model=none`. |
| `--limit N` | (none) | Process only the first N rows; useful for live-LLM smoke validation. Temporarily relaxes the batch `expected_rows` assertion. |
| `--quiet` | off | Suppress progress logging. |

## Verifying a Sweep

After the run finishes, sanity-check the headline numbers:

```bash
python3 -c "
import json
report = json.load(open('<RUN_OUT>/BATCH_02_standard_REPORT.json'))
for k in ('n_run','n_errors','task_success_rate_baseline',
          'task_success_rate_attacker','attack_success_rate',
          'elapsed_seconds'):
    print(f'{k}: {report.get(k)}')
"
```

For per-(cell, axis) aggregation use the snippet at the end of `docs/superpowers/specs/travel/task_success_metrics.md`, or re-run the aggregation Python block in `benchmark/phase5/pilot/travel_redesign_v2_20260518/SUMMARY.md` against your new RESULTS.jsonl.

## Latest Calibration Snapshot

| Sweep | TSR overall | TSR CU / MG | ASR (LLM judge) | Wall time | Notes |
|---|---:|---:|---:|---:|---|
| `travel_attack_sweep_20260517` (pre-redesign) | 45% | 22% / 68% | 4 cells at 0%, 4 cells ≥ 80% | 50 min | original asymmetry baseline |
| `travel_redesign_v2_20260518` (current) | 43% | 40% / 46% | 1 cell in band, 6 above | 51 min | redesign over-corrected; v3 dial-back proposed |

Both sit under the `<50% TSR` calibration target for `gpt-4.1-mini`. See `benchmark/phase5/pilot/travel_redesign_v2_20260518/SUMMARY.md` for the per-axis band comparison and the v3 dial-back plan.

## Source of Truth

- Loader / materializer: `clawsocialarena/generator/family_packs/travel/{loader,materialize}.py`
- Attack playbook: `clawsocialarena/attacks/stress_recipes/travel_mode_local_playbooks.py`
- LLM ASR judge: `clawsocialarena/eval/travel_asr_judge.py`
- Predicates: `clawsocialarena/eval/predicates/travel/__init__.py`
- Specs: `docs/superpowers/specs/travel/`
- Per-task scenario pages: `docs/phase_5/scenarios/travel/`
