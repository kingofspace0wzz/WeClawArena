# Bargaining Bundles

This directory contains 24 bargaining base tasks and 120 manifest rows. The
runtime family id is `marble_bargaining`.

Each base task has five matched conditions: `no_attacker`, `collaboration`,
`security`, `privacy`, and `governance`. The five manifest rows reference one
base bundle; the selected attack overlay is applied when a run is materialized.

The tasks model cross-organization purchasing and contract negotiation. Agents
must exchange offers, protect owner-scoped constraints, and complete the agreed
transaction through tool-backed state changes.

Each bundle includes `scenario.json`, `scenario.gt.json`, persona prompts, tool
declarations, resources, and any required governance state. Validate the public
release from the repository root:

```bash
uv run python scripts/validate_public_release.py
```

See the [dataset guide](../../../../docs/benchmark_dataset_guide.md) for the
shared schema and evaluation contract.
