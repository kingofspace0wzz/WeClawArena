# SWE-Workspace Bundles

This directory contains 50 SWE-Workspace base tasks and 250 manifest rows. The
runtime family id is `swebench_workspace`.

Each base task has five matched conditions: `no_attacker`, `collaboration`,
`security`, `privacy`, and `governance`. The five manifest rows reference one
base bundle; the selected attack overlay is applied when a run is materialized.

The tasks model multi-owner software implementation, review, approval, and CI
workflows. Agents operate on separate workspace resources and must satisfy the
task predicates without bypassing ownership or approval rules.

Each bundle includes `scenario.json`, `scenario.gt.json`, persona prompts, tool
declarations, and reduced repository fixtures. Validate the public release from
the repository root:

```bash
uv run python scripts/validate_public_release.py
```

The tasks use selected SWE-bench Lite issues. See the
[third-party notices](../../../../THIRD_PARTY_NOTICES.md) and the
[dataset guide](../../../../docs/benchmark_dataset_guide.md).
