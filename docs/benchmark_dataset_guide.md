# ClawSocialArena Benchmark Dataset Guide

This guide explains how to inspect the current benchmark data without reading historical design logs.

## Current Store

The active published store is:

```text
benchmark/scenarios/v2.0.0/
  manifest.json
  bargaining/
  bidding/
  travel/
  swebench_workspace/
  retail/
  research/
```

`manifest.json` has 690 rows. Each base scenario is represented by five matched modes:

```text
no_attacker
collaboration
security
privacy
governance
```

| Family | Bases | Rows | Store folder | Spec |
|---|---:|---:|---|---|
| `marble_bargaining` | 24 | 120 | `bargaining/` | `docs/superpowers/specs/bargaining/README.md` |
| `marble_bidding` | 12 | 60 | `bidding/` | `docs/superpowers/specs/bidding/README.md` |
| `travel` | 20 | 100 | `travel/` | `docs/superpowers/specs/travel/README.md` |
| `swebench_workspace` | 50 | 250 | `swebench_workspace/` | `docs/superpowers/specs/swebench_workspace/README.md` |
| `tau2_retail` | 24 | 120 | `retail/` | `docs/superpowers/specs/retail/README.md` |
| `marble_research` | 8 | 40 | `research/` | `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md` |

The older `benchmark/phase5/scaffold` tree is still useful for the 680-row baseline scaffold and 14-cell allocation history. It is not the only current benchmark target.

## Base Bundle Layout

A published base bundle normally contains:

```text
scenario.json
scenario.gt.json
family_pack_context.json
personas/
mcp/
resources/
governance/        # when applicable
phase5_metadata.json
```

`scenario.json` defines agents, prompts, tools, topology, opening state, and turn budget.

`scenario.gt.json` defines scoring contracts, including `evaluation_criteria`, resource and governance manifests, task invariants, attack plan metadata, and construction metadata.

`family_pack_context.json` carries domain-specific seed data used by tools, predicates, runtime overlays, and LLM-ASR judges.

## Runtime Variants

The published store does not need a fully copied directory for every attack row. Attack rows point to a base bundle. The runner creates per-run variants through:

```text
clawsocialarena.attacks.runtime_overlay.materialize_runtime_variant
```

The runtime variant directory records applied attack metadata in `phase5_variant_metadata.json`. Inspect that file rather than relying on manifest-level `attack_recipe` fields, which may be unset or generic.

Runtime overlays may add injected messages, file writes, or database rows. They must not directly write the final score state. Attack success must come from normal agent messages or tool calls during the run.

## Metrics

Report utility and attack success separately.

| Domain | Utility metric | Attack-success metric |
|---|---|---|
| `marble_bargaining` | raw TSR | bargaining LLM-ASR |
| `marble_bidding` | raw TSR | bidding LLM-ASR |
| `travel` | travel task success predicates | travel LLM-ASR |
| `swebench_workspace` | resource-gated task success | workspace LLM-ASR |

Deterministic attack-success columns may still appear in raw result rows. For finalized domains they are diagnostics, not headline ASR, unless the domain spec explicitly says otherwise.

No-attacker task failures can be valid benchmark signal when the run is scoreable. They should not be converted into readiness failures unless evidence is missing or the substrate failed.

## Run Artifacts

Pilot outputs usually live under `benchmark/phase5/pilot/<run_name>/`. Construction diagnostics may live under `benchmark/batches/<batch_id>/`.

Useful artifacts:

| File | Purpose |
|---|---|
| `*_RESULTS.jsonl` | Row-level simulation outputs. |
| `*_REPORT.json` or `*_REPORT.md` | Aggregated run summary. |
| `*_LLM_ASR*.jsonl` | Domain judge outputs. |
| `variants/<variant_id>/phase5_variant_metadata.json` | Applied runtime attack metadata. |
| `bundle/run/run_scorecard.json` | Task, safety, SAF, and diagnostic metrics when emitted. |
| `bundle/run/cassette.jsonl` | Replay data for LLM calls and tool calls when emitted. |
| `bundle/run/action_log.db` | Primary action log when emitted. |

For baseline runs without the full audit substrate, use the raw transcript and final-state evidence paths recorded by the scorecard or result row.

## Current Runtime Rules

- `driver_orchestrated_docker` is benchmark-valid.
- `host_session` is development-only.
- `containerized_multi_agent` remains a future stronger substrate, not a current release blocker.
- Current finalized domains should not be described as pending GPT-5.2 naturalization targets. Travel and workspace use reviewed source-derived seeds with `naturalization_model = none`; bargaining and bidding use owned-ecosystem generators.

## Historical Material

Use old batch directories and superseded specs only for debugging or audit history. Do not quote them as current benchmark design unless a current spec points to them.

Historical examples include old scaffold variants, pre-Phase-5 category sweeps, shallow bargaining rows, lightweight bidding prototype rows, pre-redesign travel sweeps, and pre-enrichment workspace sweeps.
