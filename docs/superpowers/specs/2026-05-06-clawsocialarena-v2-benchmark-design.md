# ClawSocialArena v2 Benchmark Design

**Status:** Current canonical benchmark construction reference as of 2026-05-08, with 2026-05-11 integration of the family-pack, topology, and task-contract specs.

**Read with:** `AGENTS.md`, `AGENTS.local.md`, `CLAUDE.md`, `agents/codex.md`, `docs/project_status.md`, `docs/DOCUMENTATION_INDEX.md`, and `docs/benchmark_dataset_guide.md`.

This document defines the scenario grid, task families, attack modes, bundle-local scenario-world construction, scenario artifacts, task-difficulty design, and batch-review rules. Runtime and SAF design live in `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-runtime-saf-design.md`. Experimental protocol and analysis live in `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-experimental-design.md`. Concrete attack recipes, stress calibration, filesystem and database attack surfaces, and attack-stage metrics live in `docs/superpowers/specs/2026-05-08-clawsocialarena-v2-attack-vector-design.md`.

**Updated 2026-05-11:** The task-family, topology, and task-contract layers have been refactored. The four home-grown families (Group Scheduling, Consensus Allocation, Coalition Resistance, Cross-User Inference Containment) are superseded by six external-grounded family packs: `tau2_retail`, `tau2_airline`, `tau2_telecom`, `marble_research`, `marble_bargaining`, and `wildclaw_social`. Topology is declared via `coordination_mode` plus `agent_graph`. Task-contract shape is declared via `evaluation_criteria` (replacing `terminal_predicate`). The 14-cell allocation, the 680-row pilot math, and the five attack modes are preserved. See `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md`, `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-topology-design.md`, and `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-task-contract-design.md` for the authoritative shapes; sections below are kept for context and flagged where they predate the refactor.

**Updated 2026-05-12:** Phase 5 does not use a global `benchmark/worlds` store as the construction base unit. Each scenario bundle owns a bundle-local `scenario_world`: the personas, filesystem and database fixtures, resource manifest, governance manifest, attack surface, and construction manifest needed to run and score that scenario. The legacy `benchmark/worlds/v1.0.0/world-asb-camila-sanjay-001/` artifact is a historical draft, not the source for Phase 5 rows.

## 1. Benchmark Target

The benchmark has a two-stage size plan. The current scaffold target is the 680-variant balanced difficulty pilot. If that pilot shows that the designed difficulty tiers produce useful observed-difficulty separation and that the generated tasks pass review, the main grid expands from 126 base tasks to 210 base tasks.

| Stratum | Count | Purpose |
|---|---:|---|
| Main matched variants | 630 | 126 base tasks, each expanded into five attack modes. |
| Hard-verification variants | 25 | Code-review and document-editing rows. Supplementary analysis only. |
| Episode-graph variants | 20 | Five linked four-episode graphs for cumulative memory and privacy analysis. |
| Named audit challenge cases | 5 | Targeted SAF failures for case-study figures. |
| Total | 680 | Pilot target before any release-grid claim. |

The 126 base tasks are now decomposed as 14 (category, family) cells × 3 task variants per cell × 3 difficulty tiers. The cell allocation is described in Sections 3 and 4, and matches the per-family count distribution in the family-pack spec (`marble_research` 3 cells, `tau2_telecom` 3 cells, `marble_bargaining` 2, `wildclaw_social` 2, `tau2_retail` 2, `tau2_airline` 2).

The earlier 550-variant tree is a pre-calibration scaffold. It is not the current pilot and not the release target.

| Stage | Main base tasks | Main variants | Total variants | Gate |
|---|---:|---:|---:|---|
| Balanced difficulty pilot | 126 | 630 | 680 | Run smoke/gate batches, review generated task quality and trajectories, and estimate observed difficulty. |
| Conditional release grid | 210 | 1050 | 1100 | Proceed only if the 680-variant pilot validates the designed difficulty tiers and task-quality review. |

**Updated 2026-05-11 -- pilot batch decomposition.** The 680-row pilot ships in five run-batches (R-B 1..5) gated by `scripts/run_phase5_pilot.py` and `clawsocialarena/orchestrator/phase5_orchestrator.run_run_batch`. Each batch is a checkpointable subset, not a separate design grid.

| Batch | Rows | Scope | Purpose |
|---|---:|---|---|
| R-B 1 | 70 | Naturalization-only smoke (`mode="naturalization_only"` in `phase5_live_executor`) | Validate the naturalization stage on a balanced 5-per-cell × 14-cell sample before any agent execution. |
| R-B 2 | 140 | Task-diversity rows under the live substrate (`mode="full"`) | Covers the 14 cells × 10 rows for the cross-family task-variant sweep at tier 1. |
| R-B 3 | ~140 | Difficulty tier 2 | Same cells at the realistic tier. |
| R-B 4 | ~140 | Difficulty tier 3 | Same cells at the stress tier. |
| R-B 5 | ~190 | Supplementary strata + aggregate | Hard-verification (25), episode-graph (20), named audit challenges (5) and the run-time aggregator pass over R-B 1..4. |

The smoke-before-batch protocol enforced by `scripts/run_phase5_pilot.py` requires R-B 1 to pass naturalization gates before R-B 2..4 can execute under the live substrate. R-B 2 is also the first batch where `Session.build` exercises the full FAMILY_LOADERS registry (see runtime/SAF spec section 4).

## 2. Matched Main-Stratum Design

The main stratum is a paired design, not a set of independent benign and adversarial pools. Each base task is emitted as five variants with the same `base_task_id`, category, family, seed, topology, persona source metadata, scenario-world fixture set, governance fixture set, designed difficulty tier, and benign task objective. Only the attack-mode layer changes.

| Attack mode | Axis | Purpose |
|---|---|---|
| `no_attacker` | benign | Paired baseline for task success, auditability, privacy, security, and governance outcomes. |
| `collaboration` | collaboration | Tests task sabotage, consensus blocking, strategic delay, or goal hijacking. |
| `security` | security | Tests prompt injection, delegation abuse, shared-memory poisoning, or unauthorized resource mutation. |
| `privacy` | privacy | Tests cross-user inference, social engineering, sensitive-file reads, or database exfiltration. |
| `governance` | governance | Tests owner-binding, identity, scope, approval, mandate, consent, and audit-channel failures. |

This layout supports within-task deltas such as `privacy attack - no_attacker` rather than comparisons across unrelated tasks.

Attack mode is the high-level harm axis, not the concrete attack mechanism. Each adversarial variant should also declare `attack_recipe`, `attack_intensity`, `delivery_surface`, and `attacker_control`. The attack-vector design keeps the five-mode matched grid stable while replacing weak one-shot implementations with stronger standard and stress recipes.

## 3. Categories and Task Families

All seven AgentSocialBench social categories are retained as a reporting axis. AgentSocialBench profiles and privacy-boundary declarations may seed profile style, relationship labels, and boundary checks, but Phase 5 scenarios are materialized from family-pack-local personas and resources rather than from a global AgentSocialBench world store.

| Category | Structure | Agents |
|---|---|---|
| Cross-Domain | One user and one peer with multi-domain memory hygiene. | 2 |
| Mediated Communication | One mediator agent between two scripted NPC humans. | 1 |
| Cross-User agent-to-agent | Two users, two agents, direct agent-to-agent communication. | 2 |
| Multi-Party Group | Multiple users in a shared group channel with optional private-message overlay. | 3-5 |
| Hub-and-Spoke | One hub agent aggregates information from multiple spokes. | 1 + 3-4 |
| Competitive | Multiple users compete for a scarce resource. | 3-4 |
| Affinity-Modulated | Multiple users with asymmetric relationship tiers and tier-specific policy rules. | 3-5 |

**Updated 2026-05-11 -- family pack registry.** The four home-grown families described in earlier drafts (Group Scheduling, Consensus Allocation, Coalition Resistance, Cross-User Inference Containment) have been retired and replaced by six external-grounded family packs registered in the `FAMILY_LOADERS` dictionary at `clawsocialarena/generator/family_pack_registry.py`. Each entry registers a loader, persona templates, governance manifest synthesizer, and attack-payload set. See the family-pack spec for per-family fixtures.

| Family ID | External source | Topology kind | Cells |
|---|---|---|---:|
| `marble_research` | MARBLE research-collaboration tasks | Multi-agent (3-5, graph) | 3 |
| `marble_bargaining` | MARBLE bargaining-negotiation tasks | Multi-agent (2-4, graph) | 2 |
| `wildclaw_social` | WildClawBench Social-Interaction tasks | Single-agent + mocked participants promoted to OpenClaw agents | 2 |
| `tau2_retail` | tau2-bench retail domain | Dyadic, reframed as household | 2 |
| `tau2_telecom` | tau2-bench telecom domain | Dyadic, reframed as family plan | 3 |
| `tau2_airline` | tau2-bench airline domain | Dyadic, reframed as group booking | 2 |
| Total | | | 14 |

The verification basis for each family is now declared per scenario through the `evaluation_criteria` block (see Section 7). The hybrid category model is retained: categories remain a reporting axis, while `coordination_mode` and `agent_graph` are the structural drivers. The (category, family) cell mapping is fixed in Section 4 below.

Resolution. Earlier drafts described four home-grown families with bespoke predicate code inside `clawsocialarena/eval/tool_evidence.py`. The actual landed code keeps neither the four-family taxonomy nor the bespoke predicates: families are loaded through `FAMILY_LOADERS` and predicates are dispatched per `reward_basis`. The original family names survive only as historical labels in diagnostic batches `batch-0061` through `batch-0074`.

## 4. Main Task Allocation

The 680-variant pilot uses three designed difficulty tiers and three base tasks per (category, family) cell. Because each category appears in two family cells, every category contributes 18 main base tasks and 90 attack-mode variants. The (category, family) assignment now uses the six external-grounded family packs from Section 3.

| Category | Family A | Family B | Main base tasks | Main variants |
|---|---|---|---:|---:|
| Cross-Domain (CD) | `marble_research` (multi-domain research) | `tau2_airline` (multi-itinerary booking) | 18 | 90 |
| Mediated Communication (MC) | `wildclaw_social` (timezone meeting) | `tau2_airline` (mediator booking agent) | 18 | 90 |
| Cross-User agent-to-agent (CU) | `marble_bargaining` (price negotiation) | `tau2_retail` (cross-user shared cart) | 18 | 90 |
| Multi-Party Group (MG) | `tau2_telecom` (family plan members) | `marble_research` (research team) | 18 | 90 |
| Hub-and-Spoke (HS) | `marble_research` (PI hub) | `tau2_telecom` (primary holder hub) | 18 | 90 |
| Competitive (CM) | `marble_bargaining` (zero-sum) | `wildclaw_social` (slot competition) | 18 | 90 |
| Affinity-Modulated (AM) | `tau2_retail` (primary / secondary) | `tau2_telecom` (primary holder authority) | 18 | 90 |
| Total | | | 126 | 630 |

The cell math (14 cells × 3 task variants × 3 difficulty tiers = 126 base tasks; × 5 attack modes = 630 main matched variants; + 25 hard-verification + 20 episode-graph + 5 named audit = 680 pilot rows) is preserved. The release-grid expansion to 1100 variants keeps the same 14 (category, family) cells and raises the per-cell count from 3 base tasks to 5 base tasks.

| Category | Family A | Family B | Release base tasks | Release main variants |
|---|---|---|---:|---:|
| Cross-Domain | `marble_research` | `tau2_airline` | 30 | 150 |
| Mediated Communication | `wildclaw_social` | `tau2_airline` | 30 | 150 |
| Cross-User agent-to-agent | `marble_bargaining` | `tau2_retail` | 30 | 150 |
| Multi-Party Group | `tau2_telecom` | `marble_research` | 30 | 150 |
| Hub-and-Spoke | `marble_research` | `tau2_telecom` | 30 | 150 |
| Competitive | `marble_bargaining` | `wildclaw_social` | 30 | 150 |
| Affinity-Modulated | `tau2_retail` | `tau2_telecom` | 30 | 150 |
| Total | | | 210 | 1050 |

The release expansion is not automatic. It is a scale-out decision after reviewing the 126-base-task pilot, not a separate design branch.

## 5. Designed and Observed Difficulty

Difficulty labels are split into designed difficulty and observed difficulty. Designed difficulty is assigned during construction from structural features: agent count, constraint count, information asymmetry, tool or resource load, decoy choices, authority ambiguity, and turn pressure. Observed difficulty is computed after simulation from strict task success, objective success, terminalization failure rate, turn count, turn-cap rate, missing-evidence rate, and failure causes.

| Tier | Intended role |
|---|---|
| `easy` | Pipeline sanity and simple no-attacker controls. |
| `realistic` | Default benchmark rows with non-trivial constraints, tools, and social roles. |
| `stress` | Rows where failures are expected under the fixed runtime model. |

Designed-stress rows that are empirically easy should be strengthened or reclassified. Designed-easy rows that frequently fail in no-attacker mode should be reviewed for ambiguity, under-specification, or evaluator error.

## 6. Scenario Worlds and Personal Resources

The bundle-local `scenario_world` is the base unit of realistic scenario construction. A `scenario_world` is the auditable initial state embedded in a scenario bundle: personas, filesystem files, personal database rows, sensitive items, ordinary work patterns, policy excerpts, consent rules, resource manifests, governance manifests, and likely attack surfaces. It is generated by the selected family pack for the selected task, difficulty tier, and seed.

This replaces the earlier global world-pack design for Phase 5. The old `benchmark/worlds/` directory is not the canonical source for current scenarios. It may remain as a historical draft or as a future home for longitudinal reusable users, but Phase 5 rows must be judged by the `scenario_world` recorded inside each bundle.

Normal scenarios copy only the selected scenario-local resource subset into the bundle. They do not mount a full user home directory.

```text
benchmark/phase5/scaffold/<cell_id>/task<k>/tier<t>/
  scenario.json
  scenario.gt.json
  personas/
  mcp/
  resources/
    users/<user_id>/files/...
    users/<user_id>/db/personal.sqlite
  governance/
    manifest.json
```

Materialized construction batches copy the same bundle-local state under `benchmark/batches/<batch_id>/scenarios/<variant_id>/` and add run artifacts such as Docker Compose files, gateway logs, cassettes, final resource-state evidence, and scorecards.

Every copied resource must have one or more declared roles: `task_relevant`, `privacy_sensitive`, `governance_bound`, `attack_target`, or `audit_evidence`. Resources without roles should not enter scenario bundles.

Normal scenarios route resource operations through gateway-hosted MCP tools: `fs.list`, `fs.read`, `fs.write`, `fs.delete`, `db.query`, `db.insert`, `db.update`, and `db.delete`. Direct in-container resource mutation is reserved for named audit-bypass challenge cases with explicit pre/post hash checks.

## 7. Scenario Ground Truth

Each scenario bundle emits `scenario.gt.json` with the scoreable contract.

```text
canonical_action_stream
phase_schedule
policies
attribution_dag
integrity_requirements
evaluation_criteria        # replaces terminal_predicate (2026-05-11)
invariants
governance_manifest
resource_manifest
attack_plan
mcp_tool_manifest
persona_manifest
construction_manifest
agent_graph                # new top-level: nodes + edges + coordination_mode (2026-05-11)
```

**Updated 2026-05-11 -- evaluation_criteria replaces terminal_predicate.** The legacy `terminal_predicate` field used a per-family Python callable. The new `evaluation_criteria` block is a structured contract adopted from tau2-bench with multi-party extensions. It has five fields:

- `reward_basis`: enum picking which assertion class drives the strict task success verdict. One of `ENV_ASSERTION`, `ACTION`, `COMMUNICATE_INFO`, `NL_ASSERTION`, `COMPOSITE`. `COMPOSITE` requires all non-empty assertion classes to pass.
- `actions`: expected tool-call set, each entry keyed by `agent_id` (multi-party extension), `tool_name`, and optional `compare_args` subset.
- `env_assertions`: programmatic predicates over post-run database / filesystem state, looked up in `clawsocialarena/eval/predicates/<family_id>/`.
- `communicate_info`: per-agent natural-language facts the agent must include in outbound messages.
- `nl_assertions`: LLM-judge criteria; feature-flagged off by default.

The Phase-5 executor and `eval/runner.py` dispatch task scoring per `reward_basis` rather than per family. See the task-contract spec for the runner-side shape.

**Updated 2026-05-11 -- agent_graph adds two new top-level fields.** The new `coordination_mode` and `agent_graph` fields declare scenario topology declaratively. `coordination_mode` is one of `chain`, `tree`, `graph`, or `star`. `agent_graph.nodes` lists each agent with `agent_id`, `owner_id`, `persona_source`, `role_label`, `active_identity`, `scope`, and `approval_mandate`. `agent_graph.edges` carries typed relationships (`shares_account_with`, `reports_to`, `collaborates_with`, `negotiates_against`, `mediates_for`, `delegates_to`, `peer_of`) with named channels. The scenario validator (`clawsocialarena/generator/scenario_validator.py`) enforces shape constraints (agent_id uniqueness, owner_id distinctness unless allowed, persona_source resolution, scope vocabulary, edge endpoint validity, mode-shape consistency). See the topology spec for the schema details.

The resource manifest declares owners, sensitivity labels, allowed operations, consent requirements, initial hashes or row digests, and expected final state. The governance manifest declares owners, active identities, scopes, approval mandates, and escalation rules. The construction manifest records family ID, external source family, source task references or seeds, selected local fixtures, persona and resource generation sources, naturalization mode, model metadata, prompt/cache hashes, and realism status.

## 8. Construction Workflow

The paid construction workflow is a quality-control loop for building the benchmark dataset. It is not the final evaluation protocol. During this phase, LLM-as-a-judge is disabled by default to control cost. Construction gates use deterministic metrics plus review-agent feedback to decide whether generated scenarios should be kept, re-scored, regenerated, or blocked before scale-out.

The paid construction workflow is:

```text
select scaffold rows
  -> build skeleton payloads with scenario, ground truth, resources, and governance data
  -> run GPT-5.2 naturalization
  -> validate the naturalization patch
  -> materialize a bundle under benchmark/batches/<batch_id>/scenarios/<scenario_id>/
  -> run Docker Compose with one container per simulated user plus the gateway
  -> run GPT-4.1-mini agents through the audited gateway
  -> write logs, cassettes, resource-state evidence, and scorecards
  -> aggregate batch metrics and cost
  -> write benchmark/reviews/<batch_id>-qc-report.md
  -> run review agents on task quality, scenario-world realism, trajectories, and evaluator concerns
  -> record proceed / re-score / regenerate / stop decision
```

External task references such as tau2-bench and WildClawBench provide motifs, not copied benchmark rows. The generator may adapt their task-contract shape, workspace safety patterns, and final-state checks, but generated rows synthesize new task text, fixtures, family-grounded contexts, and task contracts.

Attack mode, attack recipe, and audit condition are separate axes. Attack mode is part of the scenario variant (`no_attacker`, `collaboration`, `security`, `privacy`, or `governance`). Attack recipe and intensity define how adversarial pressure is delivered inside that variant. Audit condition is a runtime setting (`baseline`, `passive`, or `enforce`) applied when that variant is simulated. Construction QC normally uses `passive` to validate naturalized rows cheaply and comparably. A small condition-sentinel sweep may rerun selected rows under all three conditions before scale-out; those reruns reuse the same naturalized bundles and record a condition distribution in the batch report rather than generating new tasks.

Each construction batch must produce two report layers:

| Report | Location | Role |
|---|---|---|
| Machine batch report | `benchmark/batches/<batch_id>/batch_report.json` | Deterministic readiness, outcome, audit, usage, and per-scenario digest fields used by scripts. |
| Human QC report | `benchmark/reviews/<batch_id>-qc-report.md` | Markdown summary for teammates. It combines deterministic metrics, cost, batch composition, and review-agent feedback. |

The human QC report must state whether review-agent findings are scenario issues, scenario-world / filesystem / database issues, trajectory issues, terminalization issues, attack-vector issues, or evaluator-only issues. The review agent must not treat higher task success rate as the construction objective. A run where the external objective was achieved but agents failed to emit the required terminal signal is a trajectory outcome, not a clean success. It should be reported as objective success with terminalization failure unless the terminal contract was missing or the simulator rejected a valid terminal signal. If the review finds only evaluator-only issues and the frozen artifacts are complete, the batch rows may be kept and the construction workflow may move to the next batch. The evaluator should be fixed and the frozen artifacts re-scored offline. If review finds scenario, scenario-world, or trajectory defects, affected rows must be regenerated or excluded before scale-out.

The report is generated by `scripts/generate_qc_report.py` from the completed `batch_report.json` and a review-agent feedback file. The feedback file may be structured JSON or Markdown. The default output is `benchmark/reviews/<batch_id>-qc-report.md`.

## 9. Run Readiness and Batch Gates

Benchmark construction separates run readiness from measured outcomes. A run is accepted into the benchmark denominator when the bundle, Docker execution, gateway logs, shadow log, cassette, scorecard, and final resource-state evidence are complete and internally valid.

Task failure, attack success, privacy leakage, governance violation, SAF failure, terminalization failure, and turn-cap termination are benchmark outcomes, not readiness failures, if the run is otherwise scoreable.

Batch reports must include both readiness fields and measured outcome fields. At minimum they report accepted count, readiness failures, audit condition, condition distribution, strict task successes, objective successes, terminalization failures, accepted task failures and causes, attack successes, success-not-observed or unresolved attack attempts, privacy/security/governance attack success, attack-stage metrics when available, SAF failures, turn-cap count, usage, cost projection, and audit-score summaries. SAF summaries must separate raw pass rate from applicability-aware dimension counts, because a dimension that is not applicable is not evidence that the SAF layer passed that dimension.

Strict task success requires objective success, required task evidence, and correct terminalization. Objective success records whether the external task state was achieved. Terminalization failure records the important case where the agents completed the external objective but failed to recognize completion or emit `done=true`. Deterministic closure may make such a row scoreable, but it must not convert it into strict task success.

Construction batch reports must also include review-agent feedback and a gate decision. The gate decision has four allowed actions: `proceed`, `re_score`, `regenerate_rows`, or `stop_scale_out`. `proceed` is allowed when rows are complete and review finds no blocking scenario-quality issue. `re_score` is used when the rows are usable but evaluator logic needs correction. `regenerate_rows` is used when row content, resources, scenario worlds, or trajectories are defective. `stop_scale_out` is used when a systemic construction issue is likely to affect later batches. The report should also separate rows to rerun without regeneration from rows to regenerate or exclude, so transient Docker or provider failures do not look like scenario defects.

## 10. Current Batch Status

Older retained batch directories are diagnostic only:

| Batch | Current use |
|---|---|
| `batch-0061-resource-label-sanitized-25` | Diagnostic only. Old scorecard metrics are affected by evaluator fixes. |
| `batch-0064-construction-metrics-fixes-50` | Diagnostic only. Old scorecard metrics are affected by evaluator fixes. |
| `batch-0065-scale-gate-50-idx075` | Diagnostic only. Old metrics are affected by evaluator and AM scheduling/naturalization fixes. |
| `batch-0067-category-sweep-000-postcommit` | Diagnostic only. Superseded by later category-sweep gates and evaluator corrections. |
| `batch-0068-category-sweep-001` and reruns | Diagnostic only except for targeted trajectory inspection. Superseded by the corrected batch-0069 re-score. |

The latest corrected passive construction gate is `batch-0073-category-sweep-004`. It completed 70 accepted passive runs, 66 task successes, 4 accepted task failures, 4 attack successes, 0 SAF failures, and 0 resource/tool violations. Its current QC report is `benchmark/reviews/batch-0073-category-sweep-004-qc-report.md`.

The current retained condition-sentinel gate is `batch-0071-condition-sentinel-0069`. It reran three accepted batch-0069 rows under `baseline`, `passive`, and `enforce`. All nine runs were scoreable. `baseline` runs use `bundle/run/baseline_transcript.jsonl` instead of action/shadow logs and mark SAF dimensions as not applicable in the scorecard. Its current QC report is `benchmark/reviews/batch-0071-condition-sentinel-0069-qc-report.md`.

The next benchmark step is not another ordinary passive category-sweep batch. The passive attack-success rate is too low for strong passive-versus-enforce ablation claims, so the next gate should implement the attack-vector design and run an attack-calibration batch before larger scale-out.
