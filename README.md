# ClawSocialArena v2

*An auditable runtime system for benchmarking multi-party collaboration, security, privacy, and governance in human-centered agentic social networks.*

ClawSocialArena v2 is a runtime-backed benchmark. A scenario runs multiple personal-agent containers plus one ClawSocialArena audit gateway. The gateway records cross-agent messages, policy decisions, resource access, governance metadata, cassettes, and scoreable final state. Evaluation is an offline function of the action log, shadow log, cassette, ground-truth bundle, and resource evidence.

Start here:

| Need | Read |
|---|---|
| Current branch, batch, and benchmark status | [`docs/project_status.md`](docs/project_status.md) |
| Documentation map | [`docs/DOCUMENTATION_INDEX.md`](docs/DOCUMENTATION_INDEX.md) |
| Benchmark data guide | [`docs/benchmark_dataset_guide.md`](docs/benchmark_dataset_guide.md) |
| Team design spec | [`docs/superpowers/specs/2026-04-24-clawsocialarena-v2-team-design.md`](docs/superpowers/specs/2026-04-24-clawsocialarena-v2-team-design.md) |
| Runtime and SAF design | [`docs/superpowers/specs/2026-05-06-clawsocialarena-v2-runtime-saf-design.md`](docs/superpowers/specs/2026-05-06-clawsocialarena-v2-runtime-saf-design.md) |
| Benchmark construction design | [`docs/superpowers/specs/2026-05-06-clawsocialarena-v2-benchmark-design.md`](docs/superpowers/specs/2026-05-06-clawsocialarena-v2-benchmark-design.md) |
| Experimental design | [`docs/superpowers/specs/2026-05-06-clawsocialarena-v2-experimental-design.md`](docs/superpowers/specs/2026-05-06-clawsocialarena-v2-experimental-design.md) |

The old root `docs/design.md`, root `docs/plan.md`, and April 17 implementation plan are pointer stubs now. Their full historical copies live under `docs/archive/superseded/`.

## Current Status

The current working branch is `main`. The `v2-refactor` and `phase-I-governance` branches are still checked out as reference worktrees under `worktree/`; do not delete them until a separate branch cleanup review confirms that no unique useful content remains.

The active benchmark scaffold target is the 680-variant balanced difficulty pilot:

| Stratum | Count |
|---|---:|
| Main matched variants | 630 |
| Hard-verification variants | 25 |
| Episode-graph variants | 20 |
| Audit challenge cases | 5 |
| **Total** | **680** |

The old 550-variant tree is a pre-calibration scaffold, not the current final target. The retained batch directories `0061`, `0064`, and `0065` are diagnostic only because evaluator and construction fixes changed their metrics.

## Install

```bash
uv venv --python 3.11
uv pip install -e ".[dev]"
source .venv/bin/activate
```

Plain `pip install -e ".[dev]"` also works with Python 3.11+.

For the TypeScript OpenClaw channel plugin:

```bash
npx pnpm -C gateway_plugin install
```

Docker is required for live simulation batches. It is not required for many unit tests.

## Verify

Use focused verification for the area you changed. The benchmark construction path currently has focused tests such as:

```bash
.venv/bin/python -m pytest \
  tests/test_scripts/test_generate_benchmark_scaffold.py \
  tests/test_scripts/test_orchestrate_benchmark.py \
  tests/test_simulation/test_batch_runner.py \
  tests/test_eval/test_eval_runner_v2.py \
  tests/test_eval/test_leak_detector_v2.py -q
```

For the gateway plugin:

```bash
npx pnpm -C gateway_plugin test
```

## What Is In The Repository

| Path | Contents |
|---|---|
| `clawsocialarena/gateway/` | Audit gateway, session lifecycle, routes, compose runner, cassette recorder. |
| `clawsocialarena/audit/` | Action log, shadow log, MSWM, phase tracking, attribution, policies. |
| `clawsocialarena/saf/` | SAF scorers, including identity-governance auditability. |
| `clawsocialarena/eval/` | Scorecard schema, evaluator, leak detector, resource-state checks, cumulative metrics. |
| `clawsocialarena/scenario/` | Scenario models, loader, validation. |
| `clawsocialarena/generator/` | Templates, attack injection, world packs, resource overlays, naturalization support. |
| `clawsocialarena/simulation/` | LLM naturalization and Docker simulation batch runner. |
| `gateway_plugin/` | TypeScript OpenClaw channel plugin. |
| `benchmark/scenarios/v1.0.0/` | Current generated scaffold. Check `build_report.json` before trusting counts. |
| `benchmark/batches/` | Retained paid smoke/gate runs. Current retained runs are diagnostic only. |
| `docs/` | Current docs, archived historical docs, and design/plan references. |

## Current Benchmark Next Step

Run the first passive attack-calibration gate before further scale-out. This batch selects stress-tier adversarial rows across the seven main categories and four attack modes, then reports attack recipe, intensity, and stage metrics:

```bash
.venv/bin/python scripts/naturalize_and_run_batch.py \
  --batch-id batch-0074-attack-calibration-000 \
  --batch-strategy attack-calibration \
  --batch-size 28 \
  --out benchmark/batches \
  --max-cost-usd 25 \
  --construction-model gpt-5.2 \
  --agent-model gpt-4.1-mini \
  --naturalization-attempts 3 \
  --simulation-attempts 2 \
  --condition passive
```

Review the generated tasks, simulation trajectories, task success rate, attack success rate, attack-stage metrics, SAF scores, and audit summaries before running the next gate.

## License

Apache-2.0. See `pyproject.toml`.
