# MARBLE Bargaining v2.0.0 Run Guide

This directory contains the 24 published MARBLE bargaining base scenarios:

- `CU-A-marble_bargaining__t0` through `CU-A-marble_bargaining__t11`
- `CM-A-marble_bargaining__t0` through `CM-A-marble_bargaining__t11`

The current v2.0.0 manifest has five bargaining modes total:

- `no_attacker`
- `collaboration`
- `security`
- `privacy`
- `governance`

The four non-baseline modes are the attack axes. A full bargaining sweep is therefore `24 base scenarios x 5 modes = 120 simulation rows`.

## Prerequisites

Run commands from the repository root.

Docker must be running. The runner starts real Docker-backed gateway containers for each simulation row.

Load credentials from the repo-local `.env` file before paid runs:

```bash
set -a
source .env
set +a
```

Use the repo virtual environment:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_scripts/test_run_bargaining_stress_calibration.py -q
```

## Full No-Attacker Plus Attack Sweep

This runs all 24 bargaining base scenarios across the current five manifest modes, using the same simulation model and turn cap used in the latest bargaining calibration:

```bash
PYTHONPATH=. .venv/bin/python scripts/run_bargaining_stress_calibration.py \
  --store benchmark/scenarios/v2.0.0 \
  --out-dir benchmark/phase5/pilot/bargaining_owned_ecosystem_5_modes_cap36_$(date +%Y%m%d) \
  --agent-model gpt-4.1-mini \
  --max-turns 36 \
  --modes no_attacker,collaboration,security,privacy,governance \
  --audit-condition passive \
  --simulation-attempts 1
```

The runner writes:

- `BARGAINING_STRESS_RESULTS.jsonl`: one `ScenarioResult` row per simulation.
- `BARGAINING_STRESS_REPORT.json`: aggregate TSR, turn-cap, token, and diagnostic ASR summary.

Deterministic ASR fields in this report are retained as diagnostics. Bargaining ASR should be reported from the LLM-ASR judge output.

## Common Run Slices

Run only the no-attacker baseline rows:

```bash
PYTHONPATH=. .venv/bin/python scripts/run_bargaining_stress_calibration.py \
  --store benchmark/scenarios/v2.0.0 \
  --out-dir benchmark/phase5/pilot/bargaining_no_attacker_cap36_$(date +%Y%m%d) \
  --agent-model gpt-4.1-mini \
  --max-turns 36 \
  --modes no_attacker \
  --audit-condition passive \
  --simulation-attempts 1
```

Run only the four non-baseline attack modes:

```bash
PYTHONPATH=. .venv/bin/python scripts/run_bargaining_stress_calibration.py \
  --store benchmark/scenarios/v2.0.0 \
  --out-dir benchmark/phase5/pilot/bargaining_attack_only_cap36_$(date +%Y%m%d) \
  --agent-model gpt-4.1-mini \
  --max-turns 36 \
  --attack-only \
  --modes collaboration,security,privacy,governance \
  --audit-condition passive \
  --simulation-attempts 1
```

Smoke-test one base scenario before spending the full sweep:

```bash
PYTHONPATH=. .venv/bin/python scripts/run_bargaining_stress_calibration.py \
  --store benchmark/scenarios/v2.0.0 \
  --out-dir /tmp/clawsocialarena_bargaining_smoke \
  --agent-model gpt-4.1-mini \
  --max-turns 36 \
  --base-id CU-A-marble_bargaining__t0 \
  --modes no_attacker,governance \
  --audit-condition passive \
  --simulation-attempts 1
```

`--base-id` can be supplied more than once to run a small hand-picked subset.

## Changing The Simulation Model

The simulation agents are controlled by `--agent-model`.

For example, to run the same sweep with `gpt-5.2` as the simulated agent model:

```bash
PYTHONPATH=. .venv/bin/python scripts/run_bargaining_stress_calibration.py \
  --store benchmark/scenarios/v2.0.0 \
  --out-dir benchmark/phase5/pilot/bargaining_owned_ecosystem_5_modes_cap36_gpt52_$(date +%Y%m%d) \
  --agent-model gpt-5.2 \
  --max-turns 36 \
  --modes no_attacker,collaboration,security,privacy,governance \
  --audit-condition passive \
  --simulation-attempts 1
```

The materialization model is not used by this sweep script because these v2.0.0 scenario bundles are already materialized. To regenerate or republish scenario bundles, use the publishing/materialization pipeline separately and set its naturalization/materialization model there.

## LLM-ASR Judge

After a sweep finishes, run the bargaining-specific LLM-ASR judge over the JSONL results:

```bash
RUN_DIR=benchmark/phase5/pilot/bargaining_owned_ecosystem_5_modes_cap36_YYYYMMDD

PYTHONPATH=. .venv/bin/python -m clawsocialarena.eval.bargaining_asr_judge \
  --batch-results "$RUN_DIR/BARGAINING_STRESS_RESULTS.jsonl" \
  --out "$RUN_DIR/BARGAINING_STRESS_RESULTS.llm_asr.jsonl" \
  --base-dir . \
  --judge-model gpt-5.2 \
  --max-workers 4
```

Change the judge model with `--judge-model`. This is independent from `--agent-model`; `--agent-model` controls the simulation agents, while `--judge-model` controls post-hoc ASR scoring.

For a cheap judge smoke test:

```bash
PYTHONPATH=. .venv/bin/python -m clawsocialarena.eval.bargaining_asr_judge \
  --batch-results "$RUN_DIR/BARGAINING_STRESS_RESULTS.jsonl" \
  --out "$RUN_DIR/BARGAINING_STRESS_RESULTS.llm_asr.smoke.jsonl" \
  --base-dir . \
  --judge-model gpt-5.2 \
  --limit 3 \
  --max-workers 1
```

