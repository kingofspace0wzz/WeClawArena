# Trading Bundles

This directory contains 8 synthetic trading base tasks and 40 manifest rows.
The runtime family id is `claw_trading`.

Each base task has five matched conditions: `no_attacker`, `collaboration`,
`security`, `privacy`, and `governance`. The five manifest rows reference one
base bundle; the selected attack overlay is applied when a run is materialized.

The tasks model investment-club proposals, portfolio analysis, member voting,
and trade execution. Agents must follow mandate and approval rules while
protecting member-scoped financial information. The dataset is a benchmark
artifact and does not provide investment advice.

Each bundle includes `scenario.json`, `scenario.gt.json`, persona prompts, tool
declarations, owner-scoped resources, and governance state. Validate one bundle
from the repository root:

```bash
uv run python -m clawsocialarena.scenario.validate \
  benchmark/scenarios/v2.0.0/trading/CU-E-claw_trading__t4
```

See the [dataset guide](../../../../docs/benchmark_dataset_guide.md) for the
shared schema and evaluation contract.
