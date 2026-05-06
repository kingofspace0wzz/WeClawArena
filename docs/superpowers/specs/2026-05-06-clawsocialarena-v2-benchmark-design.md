# ClawSocialArena v2 Benchmark Design

**Status:** Current canonical benchmark construction reference as of 2026-05-06.

**Read with:** `AGENTS.md`, `AGENTS.local.md`, `CLAUDE.md`, `agents/codex.md`, `docs/project_status.md`, `docs/DOCUMENTATION_INDEX.md`, and `docs/benchmark_dataset_guide.md`.

This document defines the scenario grid, task families, attack modes, world-pack construction, scenario artifacts, task-difficulty design, and batch-review rules. Runtime and SAF design live in `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-runtime-saf-design.md`. Experimental protocol and analysis live in `docs/superpowers/specs/2026-05-06-clawsocialarena-v2-experimental-design.md`.

## 1. Benchmark Target

The benchmark has a two-stage size plan. The current scaffold target is the 680-variant balanced difficulty pilot. If that pilot shows that the designed difficulty tiers produce useful observed-difficulty separation and that the generated tasks pass review, the main grid expands from 126 base tasks to 210 base tasks.

| Stratum | Count | Purpose |
|---|---:|---|
| Main matched variants | 630 | 126 base tasks, each expanded into five attack modes. |
| Hard-verification variants | 25 | Code-review and document-editing rows. Supplementary analysis only. |
| Episode-graph variants | 20 | Five linked four-episode graphs for cumulative memory and privacy analysis. |
| Named audit challenge cases | 5 | Targeted SAF failures for case-study figures. |
| Total | 680 | Pilot target before any release-grid claim. |

The earlier 550-variant tree is a pre-calibration scaffold. It is not the current pilot and not the release target.

| Stage | Main base tasks | Main variants | Total variants | Gate |
|---|---:|---:|---:|---|
| Balanced difficulty pilot | 126 | 630 | 680 | Run smoke/gate batches, review generated task quality and trajectories, and estimate observed difficulty. |
| Conditional release grid | 210 | 1050 | 1100 | Proceed only if the 680-variant pilot validates the designed difficulty tiers and task-quality review. |

## 2. Matched Main-Stratum Design

The main stratum is a paired design, not a set of independent benign and adversarial pools. Each base task is emitted as five variants with the same `base_task_id`, category, family, seed, topology, persona source metadata, filesystem / database fixture set, governance fixture set, designed difficulty tier, and benign task objective. Only the attack-mode layer changes.

| Attack mode | Axis | Purpose |
|---|---|---|
| `no_attacker` | benign | Paired baseline for task success, auditability, privacy, security, and governance outcomes. |
| `collaboration` | collaboration | Tests task sabotage, consensus blocking, strategic delay, or goal hijacking. |
| `security` | security | Tests prompt injection, delegation abuse, shared-memory poisoning, or unauthorized resource mutation. |
| `privacy` | privacy | Tests cross-user inference, social engineering, sensitive-file reads, or database exfiltration. |
| `governance` | governance | Tests owner-binding, identity, scope, approval, mandate, consent, and audit-channel failures. |

This layout supports within-task deltas such as `privacy attack - no_attacker` rather than comparisons across unrelated tasks.

## 3. Categories and Task Families

All seven AgentSocialBench social categories are retained. Profiles and privacy-boundary declarations are used as user profile sources for normal benchmark users.

| Category | Structure | Agents |
|---|---|---|
| Cross-Domain | One user and one peer with multi-domain memory hygiene. | 2 |
| Mediated Communication | One mediator agent between two scripted NPC humans. | 1 |
| Cross-User agent-to-agent | Two users, two agents, direct agent-to-agent communication. | 2 |
| Multi-Party Group | Multiple users in a shared group channel with optional private-message overlay. | 3-5 |
| Hub-and-Spoke | One hub agent aggregates information from multiple spokes. | 1 + 3-4 |
| Competitive | Multiple users compete for a scarce resource. | 3-4 |
| Affinity-Modulated | Multiple users with asymmetric relationship tiers and tier-specific policy rules. | 3-5 |

The main grid uses four tau2-style verifiable task families.

| Family | Assigned categories | Verification basis |
|---|---|---|
| Group Scheduling | Mediated Communication, Cross-User agent-to-agent, Affinity-Modulated | Calendar state satisfies duration, availability, participant, and confirmation constraints. |
| Consensus Allocation | Cross-Domain, Multi-Party Group, Hub-and-Spoke, Competitive | Ledger or allocation state satisfies fairness, priority, budget, or quorum rules. |
| Coalition Resistance | Cross-User agent-to-agent, Multi-Party Group, Hub-and-Spoke, Competitive | Final manifest, runbook, or review state includes legitimate actors and excludes forbidden actors. |
| Cross-User Inference Containment | Cross-Domain, Mediated Communication, Affinity-Modulated | Required allowed answer is delivered while privacy invariants remain unbreached. |

## 4. Main Task Allocation

The 680-variant pilot uses three designed difficulty tiers and three base tasks per category/family/tier cell. Because each category appears in two family cells, every category contributes 18 main base tasks and 90 attack-mode variants.

| Category | Included families | Main base tasks | Main variants |
|---|---|---:|---:|
| Cross-Domain | Consensus Allocation, Cross-User Inference Containment | 18 | 90 |
| Mediated Communication | Group Scheduling, Cross-User Inference Containment | 18 | 90 |
| Cross-User agent-to-agent | Group Scheduling, Coalition Resistance | 18 | 90 |
| Multi-Party Group | Consensus Allocation, Coalition Resistance | 18 | 90 |
| Hub-and-Spoke | Consensus Allocation, Coalition Resistance | 18 | 90 |
| Competitive | Consensus Allocation, Coalition Resistance | 18 | 90 |
| Affinity-Modulated | Group Scheduling, Cross-User Inference Containment | 18 | 90 |
| Total | 14 category/family cells | 126 | 630 |

The conditional release grid keeps the same 14 category/family cells and three designed difficulty tiers, but raises the per-cell count from three base tasks to five base tasks. That gives each category 30 base tasks and 150 main variants.

| Category | Included families | Release base tasks | Release main variants |
|---|---|---:|---:|
| Cross-Domain | Consensus Allocation, Cross-User Inference Containment | 30 | 150 |
| Mediated Communication | Group Scheduling, Cross-User Inference Containment | 30 | 150 |
| Cross-User agent-to-agent | Group Scheduling, Coalition Resistance | 30 | 150 |
| Multi-Party Group | Consensus Allocation, Coalition Resistance | 30 | 150 |
| Hub-and-Spoke | Consensus Allocation, Coalition Resistance | 30 | 150 |
| Competitive | Consensus Allocation, Coalition Resistance | 30 | 150 |
| Affinity-Modulated | Group Scheduling, Cross-User Inference Containment | 30 | 150 |
| Total | 14 category/family cells | 210 | 1050 |

The release expansion is not automatic. It is a scale-out decision after reviewing the 126-base-task pilot, not a separate design branch.

## 5. Designed and Observed Difficulty

Difficulty labels are split into designed difficulty and observed difficulty. Designed difficulty is assigned during construction from structural features: agent count, constraint count, information asymmetry, tool or resource load, decoy choices, authority ambiguity, and turn pressure. Observed difficulty is computed after simulation from task success, turn count, turn-cap rate, missing-evidence rate, and failure causes.

| Tier | Intended role |
|---|---|
| `easy` | Pipeline sanity and simple no-attacker controls. |
| `realistic` | Default benchmark rows with non-trivial constraints, tools, and social roles. |
| `stress` | Rows where failures are expected under the fixed runtime model. |

Designed-stress rows that are empirically easy should be strengthened or reclassified. Designed-easy rows that frequently fail in no-attacker mode should be reviewed for ambiguity, under-specification, or evaluator error.

## 6. World Packs and Personal Resources

The user world pack is the base unit of realistic scenario construction. A world pack starts from AgentSocialBench user profiles and privacy-boundary declarations, then extends them with synthetic filesystem state, personal database records, sensitive items, ordinary work patterns, policies, consent rules, and likely attack surfaces.

Normal scenarios copy only the selected scenario-local resource subset into the bundle. They do not mount a full user home directory.

```text
benchmark/scenarios/v1.0.0/main/<category>/<family>/<scenario_id>/
  scenario.json
  scenario.gt.json
  docker-compose.yml
  personas/
  mcp/
  resources/
    users/<user_id>/files/...
    users/<user_id>/db/personal.sqlite
  governance/
    manifest.json
```

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
terminal_predicate
invariants
governance_manifest
resource_manifest
attack_plan
mcp_tool_manifest
persona_manifest
construction_manifest
```

The resource manifest declares owners, sensitivity labels, allowed operations, consent requirements, initial hashes or row digests, and expected final state. The governance manifest declares owners, active identities, scopes, approval mandates, and escalation rules. The construction manifest records profile sources, world-pack IDs, selected resources, naturalization mode, model metadata, prompt/cache hashes, and realism status.

## 8. Construction Workflow

The paid construction workflow is:

```text
select scaffold rows
  -> build skeleton payloads with scenario, ground truth, resources, and governance data
  -> run GPT-5 naturalization
  -> validate the naturalization patch
  -> materialize a bundle under benchmark/batches/<batch_id>/scenarios/<scenario_id>/
  -> run Docker Compose with one container per simulated user plus the gateway
  -> run GPT-4.1-mini agents through the audited gateway
  -> write logs, cassettes, resource-state evidence, and scorecards
  -> aggregate batch metrics and cost
  -> stop for review
```

External task references such as tau2-bench and WildClawBench provide motifs, not copied benchmark rows. The generator may adapt their task-contract shape, workspace safety patterns, and final-state checks, but generated rows synthesize new task text, fixtures, profile-grounded contexts, and terminal predicates.

## 9. Run Readiness and Batch Gates

Benchmark construction separates run readiness from measured outcomes. A run is accepted into the benchmark denominator when the bundle, Docker execution, gateway logs, shadow log, cassette, scorecard, and final resource-state evidence are complete and internally valid.

Task failure, attack success, privacy leakage, governance violation, SAF failure, and turn-cap termination are benchmark outcomes, not readiness failures, if the run is otherwise scoreable.

Batch reports must include both readiness fields and measured outcome fields. At minimum they report accepted count, readiness failures, task successes, accepted task failures and causes, attack successes, attack resistance, privacy/security/governance attack success, SAF failures, turn-cap count, usage, cost projection, and audit-score summaries.

## 10. Current Batch Status

The retained batch directories are diagnostic only:

| Batch | Current use |
|---|---|
| `batch-0061-resource-label-sanitized-25` | Diagnostic only. Old scorecard metrics are affected by evaluator fixes. |
| `batch-0064-construction-metrics-fixes-50` | Diagnostic only. Old scorecard metrics are affected by evaluator fixes. |
| `batch-0065-scale-gate-50-idx075` | Diagnostic only. Old metrics are affected by evaluator and AM scheduling/naturalization fixes. |

The next benchmark step is to rerun corrected replacement gates from indexes `0`, `25`, and `75`, review generated task quality and trajectories between gates, then continue scale-out only if review passes.
