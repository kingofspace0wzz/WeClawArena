# Clinical Bundles

This directory contains 10 synthetic clinical base tasks and 50 manifest rows.
The runtime family id is `claw_clinical`.

Each base task has five matched conditions: `no_attacker`, `collaboration`,
`security`, `privacy`, and `governance`. The five manifest rows reference one
base bundle; the selected attack overlay is applied when a run is materialized.

The tasks model care-team coordination over synthetic patient records. Agents
must assemble an appropriate care action while respecting consent, role,
minimum-necessary disclosure, and approval constraints. The dataset is a
benchmark artifact and is not intended for clinical decision-making.

Each bundle includes `scenario.json`, `scenario.gt.json`, persona prompts, tool
declarations, owner-scoped resources, and governance state. Validate one bundle
from the repository root:

```bash
uv run python -m clawsocialarena.scenario.validate \
  benchmark/scenarios/v2.0.0/clinical/CM-D-claw_clinical__t5
```

See the [dataset guide](../../../../docs/benchmark_dataset_guide.md) for the
shared schema and evaluation contract.
