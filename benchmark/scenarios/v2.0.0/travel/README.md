# Travel Bundles

This directory contains 20 travel base tasks and 100 manifest rows. The runtime
family id is `travel`.

Each base task has five matched conditions: `no_attacker`, `collaboration`,
`security`, `privacy`, and `governance`. The five manifest rows reference one
base bundle; the selected attack overlay is applied when a run is materialized.

The tasks model group and delegated travel planning across traveler, partner,
organizer, and approver roles. Agents must satisfy itinerary and policy
constraints while respecting owner-scoped profile and budget data.

Each bundle includes `scenario.json`, `scenario.gt.json`, persona prompts, tool
declarations, and owner-scoped resources. Validate the public release from the
repository root:

```bash
uv run python scripts/validate_public_release.py
```

The tasks use adapted TravelBench seeds. See the
[third-party notices](../../../../THIRD_PARTY_NOTICES.md) and the
[dataset guide](../../../../docs/benchmark_dataset_guide.md).
