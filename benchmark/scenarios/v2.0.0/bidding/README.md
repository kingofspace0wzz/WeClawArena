# Bidding Bundles

This directory contains 12 bidding base tasks and 60 manifest rows. The runtime
family id is `marble_bidding`.

Each base task has five matched conditions: `no_attacker`, `collaboration`,
`security`, `privacy`, and `governance`. The five manifest rows reference one
base bundle; the selected attack overlay is applied when a run is materialized.

The tasks model multi-party procurement and award decisions. Agents compare
bids, follow owner constraints, and produce tool-backed selection outcomes
without disclosing protected commercial information.

Each bundle includes `scenario.json`, `scenario.gt.json`, persona prompts, tool
declarations, resources, and any required governance state. Validate the public
release from the repository root:

```bash
uv run python scripts/validate_public_release.py
```

See the [dataset guide](../../../../docs/benchmark_dataset_guide.md) for the
shared schema and evaluation contract.
