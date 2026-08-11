# WeClawArena Benchmark Dataset Guide

This guide describes the finalized WeClawArena v2.0.0 scenario store.

## Release Summary

The canonical store is `benchmark/scenarios/v2.0.0/manifest.json` plus six domain directories.

| Domain directory | Family id | Base tasks | Manifest rows |
|---|---|---:|---:|
| `bargaining/` | `marble_bargaining` | 24 | 120 |
| `bidding/` | `marble_bidding` | 12 | 60 |
| `travel/` | `travel` | 20 | 100 |
| `swebench_workspace/` | `swebench_workspace` | 50 | 250 |
| `clinical/` | `claw_clinical` | 10 | 50 |
| `trading/` | `claw_trading` | 8 | 40 |
| **Total** | | **124** | **620** |

Each base task has five manifest rows: `no_attacker`, `collaboration`, `security`, `privacy`, and `governance`.

## Manifest Rows

Each row in `manifest.json` contains:

| Field | Meaning |
|---|---|
| `variant_id` | Unique `<base_id>__<attack_mode>` identifier |
| `base_id` | Identifier of the shared base bundle |
| `base_scenario_id` | Base identifier used by the runtime |
| `bundle_dir` | Domain-relative base bundle path |
| `cell_id` | Task cell or topology grouping |
| `family_id` | Runtime family-pack identifier |
| `task_index` | Task number within the family or cell |
| `tier_index` | Optional difficulty tier |
| `attack_mode` | One of the five matched conditions |
| `stratum` | Benchmark reporting stratum |

Five variant rows point to the same `bundle_dir`. The runtime copies that base bundle and applies the selected attack overlay for non-control rows.

## Base Bundle

A bundle contains the scenario and the owner-scoped environment needed to materialize a run:

```text
<domain>/<base_id>/
  scenario.json
  scenario.gt.json
  family_pack_context.json
  docker-compose.yml
  personas/
    <agent_id>.system.md
    <agent_id>.tools.json
  mcp/
    <tool_name>.json
  resources/
  governance/              # when governed actions are present
  resources_initial/       # when resettable state is shipped separately
  phase5_metadata.json     # construction metadata in applicable domains
  naturalization_record.json
```

The `phase5_metadata.json` filename is retained for compatibility with the current runtime. It is construction metadata inside a released bundle, not a Phase 5 execution record.

### `scenario.json`

This file defines the scenario id, task family, agents, owner identities, allowed tools, coordination topology, initial state, opening message, and turn limit.

### `scenario.gt.json`

This file defines the ground-truth task contract, including canonical actions, terminal predicates, evaluation criteria, resource rules, governance rules, attack-audit fields, and construction metadata.

### Personas And Tools

Each agent has a system prompt and an allowed-tool list under `personas/`. Tool declarations under `mcp/` map the bundle contract to gateway routes. The gateway checks owner identity and scope when tools operate on files, tables, policies, or governed actions.

### Resources

Resources model owner-local files, SQLite state, task artifacts, and policy records. Some families ship both `resources_initial/` and `resources/`; the initial directory provides resettable input state, while the runtime copy is mutable during a run.

## Attack Conditions

| Mode | Harm surface |
|---|---|
| `no_attacker` | Benign matched control |
| `collaboration` | Goal hijack, false handoff, blocked consensus, or poisoned shared plan |
| `security` | Poisoned evidence, unsafe tool use, forbidden mutation, or false execution claim |
| `privacy` | Disclosure of protected owner, patient, budget, strategy, or workspace information |
| `governance` | Identity confusion, missing consent, forged approval, or invalid mandate |

Attack variants are created at run time by `clawsocialarena.attacks.runtime_overlay.materialize_runtime_variant`. The base dataset does not store five full copies of each task.

## Evaluation Contract

Task success and attack success are separate outcomes.

- Task success is computed from required tool actions, final workspace predicates, or both.
- Attack success checks whether the specified final harm occurred and whether bounded evidence connects it to the attack condition.
- A scoreable task failure remains a task result. It is not automatically an infrastructure error.
- A successful task may still have a successful attack.

The exact evaluator depends on the domain. `clawsocialarena/eval/` contains deterministic predicates, task evaluators, and bounded-evidence ASR judges.

## Validation

Run the public release contract check:

```bash
uv run python scripts/validate_public_release.py
```

Validate an individual bundle:

```bash
uv run python -m clawsocialarena.scenario.validate \
  benchmark/scenarios/v2.0.0/clinical/CM-D-claw_clinical__t5
```

The release validator checks the six-domain allowlist, 124/620 totals, five-mode matching, unique identifiers, bundle paths, required files, public metadata, README links, and excluded Git paths.

## Runtime Outputs

New runs should write to an ignored local output directory such as `output/runs/<run_id>/`. Typical records include result JSONL, scorecards, cassettes, action logs, simulation reports, and materialized variants. Those records are generated by the user and are outside the v2.0.0 dataset snapshot.

## Source Notices

Travel bundles use adapted TravelBench task seeds. SWE-Workspace bundles use selected SWE-bench Lite issues and reduced fixtures from named upstream repositories. See [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) for citations and license notes.
