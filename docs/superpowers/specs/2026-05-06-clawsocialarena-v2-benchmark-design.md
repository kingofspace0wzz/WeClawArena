# ClawSocialArena v2 Benchmark Design

**Status:** Current compact benchmark construction reference as of 2026-05-20.

Read with:

- `docs/project_status.md`
- `docs/DOCUMENTATION_INDEX.md`
- `docs/benchmark_dataset_guide.md`
- `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-runtime-saf-design.md`
- `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-experimental-design.md`
- `docs/superpowers/specs/2026-05-08-clawsocialarena-v2-attack-vector-design.md`

## Current Target

The active published scenario store is `benchmark/scenarios/v2.0.0`. Its manifest has 690 rows across six published families.

| Family | Bases | Rows | Current role |
|---|---:|---:|---|
| `marble_bargaining` | 24 | 120 | Finalized owned-ecosystem bargaining slice. |
| `marble_bidding` | 12 | 60 | Finalized owned-ecosystem bidding slice. |
| `travel` | 20 | 100 | Finalized TravelBench-derived travel slice. |
| `swebench_workspace` | 50 | 250 | Finalized SWE-bench Lite owned-workspace slice. |
| `tau2_retail` | 24 | 120 | Published retail slice. |
| `marble_research` | 8 | 40 | Published research slice. |
| **Total** | **138** | **690** | Active v2.0.0 manifest. |

Each base has five matched modes:

```text
no_attacker
collaboration
security
privacy
governance
```

The older `benchmark/phase5/scaffold` tree remains the baseline 680-row scaffold and historical 14-cell allocation reference. It should not be treated as the only current benchmark target.

## Current Domain Boundaries

| Domain | Construction summary | Current detailed spec |
|---|---|---|
| `marble_bargaining` | Buyer, seller, and approver close one valid owned-ecosystem transaction. | `docs/superpowers/specs/bargaining/README.md` |
| `marble_bidding` | Seller awards a public bid; winning buyer confirms; buyer and seller write consistent close artifacts. | `docs/superpowers/specs/bidding/README.md` |
| `travel` | TravelBench hotel-booking seeds become CU-D triads and MG-C groups with bargaining bounds, approvals, and consent collection. | `docs/superpowers/specs/travel/README.md` |
| `swebench_workspace` | SWE-bench Lite tasks become four-owner engineering workspaces with implementer, reviewer, code-owner, and CI-owner resources. | `docs/superpowers/specs/swebench_workspace/README.md` |

`tau2_retail` and `marble_research` remain published family-pack slices. Their older family-pack details are in `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md`.

## Scenario Bundle Contract

A base bundle is the scoreable unit. It owns its local personas, resources, governance data, tool manifests, and task contract.

Required core files:

```text
scenario.json
scenario.gt.json
family_pack_context.json
personas/
mcp/
resources/
governance/        # when applicable
```

`scenario.json` declares:

- agents and owners
- prompts
- topology
- allowed tools
- turn budget
- initial messages

`scenario.gt.json` declares:

- `evaluation_criteria`
- resource manifest
- governance manifest
- invariants
- attack plan metadata
- construction metadata

`family_pack_context.json` carries the domain-specific seed facts consumed by tools, predicates, overlays, and LLM-ASR judges.

## Task Contract

Task success is declared through `evaluation_criteria`, not legacy `terminal_predicate` logic.

The supported assertion channels are:

- `actions`
- `env_assertions`
- `communicate_info`
- `nl_assertions`

The `reward_basis` field controls how strict success is resolved. Domain-specific predicates live under `clawsocialarena.eval.predicates.<family_id>`.

For finalized domains, use the compact domain specs for exact pass criteria. Examples:

- bargaining and bidding use raw TSR over owned close artifacts
- travel uses travel predicates and travel-specific auxiliary checks
- `swebench_workspace` uses the resource-gated coding workflow and evidence chain

## Runtime Variant Contract

Published attack rows point to base bundles. Runtime variants are materialized on demand through:

```text
clawsocialarena.attacks.runtime_overlay.materialize_runtime_variant
```

Runtime overlays may add attacker messages, resource file writes, or database rows. They must not directly write final score state. Final harm must arise from the agents' normal messages or tool calls.

Inspect `phase5_variant_metadata.json` in the run output to identify the applied recipe, payload, target agents, delivery surfaces, and judge metadata.

## Runtime Substrate

`driver_orchestrated_docker` is the benchmark-valid substrate. A valid run routes scored messages, tools, resource operations, model-call records, and run artifacts through the gateway and Docker-backed bundle.

`host_session` is development-only. `containerized_multi_agent` remains a possible stronger future substrate, not a current blocker.

## Readiness Versus Outcomes

Readiness failures exclude rows from denominators. Examples include malformed bundles, missing logs, missing scorecards, broken hash chains, evaluator crashes, and unscorable final state.

Task failure, attack success, privacy leakage, governance violation, turn-cap termination, and failed no-attacker rows are benchmark outcomes when evidence is complete.

## Reporting Rule

Keep utility and attack success separate:

- Utility: TSR or task success, turn caps, runtime errors, stage coverage.
- Attack success: domain LLM-ASR for bargaining, bidding, travel, and `swebench_workspace`.
- Deterministic attack-success columns: diagnostics unless a domain spec says otherwise.

## Historical References

The 680-row scaffold, older six-family allocation, and earlier stress-design drafts are retained for history. Use them only when debugging old batches or when a current spec explicitly references them.
