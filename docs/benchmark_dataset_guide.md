# ClawSocialArena Benchmark Dataset Guide

This document explains the current benchmark design and the data generated so far. It is intended for teammates who need to inspect scenario folders, simulation runs, and evaluation reports without first reading the full project spec.

## 1. Current Status

Read `docs/project_status.md` for the latest branch, batch, and benchmark state. This guide explains the dataset layout and the current benchmark design.

The current canonical scaffold path is `benchmark/scenarios/v1.0.0`. The active scaffold target is the 680-variant balanced difficulty pilot:

| Stratum | Count | Current role |
|---|---:|---|
| Main matched variants | 630 | Balanced difficulty pilot. 126 base tasks, each expanded into five attack modes. |
| Hard-verification rows | 25 | Supplementary code-review and document-editing tasks. |
| Episode-graph rows | 20 | Five linked 4-episode graphs for cumulative memory and privacy analysis. |
| Audit challenge cases | 5 | Hand-authored cases for targeted SAF failures. |

The scaffold is not by itself final benchmark data. It is a structured input to LLM naturalization, Docker simulation, scoring, and human review. Build reports that mark `realism_status: worldpack_draft` and `release_ready: false` should be treated as readiness artifacts, not release claims.

The earlier 550-variant tree is a pre-calibration scaffold. The later recommended release grid may expand to 1100 total variants, including 1050 main variants, if the 680-variant pilot shows useful separation between designed and observed difficulty.

| Stage | Main base tasks | Main variants | Total variants | Status |
|---|---:|---:|---:|---|
| Balanced difficulty pilot | 126 | 630 | 680 | Active target. |
| Conditional release grid | 210 | 1050 | 1100 | Proceed only after pilot task-quality and observed-difficulty review. |

The paid smoke data lives under `benchmark/batches/`. These runs use `gpt-5` for construction naturalization and `gpt-4.1-mini` for all simulated agents. The retained batches are currently diagnostic only because evaluator and construction fixes changed score semantics.

## 2. Main Scenario Layout

The main stratum is a matched design. Each base task has five variants with the same `base_task_id`, category, task family, users, resources, governance fixtures, and benign task objective. Only the attack mode changes.

| Attack mode | Meaning |
|---|---|
| `no_attacker` | Benign paired control. |
| `collaboration` | Task sabotage, consensus blocking, or goal hijacking. |
| `security` | Prompt injection, delegation abuse, memory poisoning, or resource damage. |
| `privacy` | Cross-user inference, social engineering, sensitive-file read, or database exfiltration. |
| `governance` | Owner, identity, scope, approval, mandate, consent, or audit-channel failure. |

The 14 main category/family cells are:

| Family | Categories |
|---|---|
| Scheduling | Cross-User agent-to-agent, Mediated Communication, Affinity-Modulated |
| Consensus | Cross-Domain, Multi-Party Group, Hub-and-Spoke, Competitive |
| Inference containment | Cross-Domain, Mediated Communication, Affinity-Modulated |
| Coalition resistance | Cross-User agent-to-agent, Multi-Party Group, Hub-and-Spoke, Competitive |

The 680-variant pilot uses 126 main base tasks. The `main variants` column counts the five attack-mode variants generated from each base task.

| Category | Included families | Main base tasks | Main variants |
|---|---|---:|---:|
| Cross-User agent-to-agent | Scheduling, Coalition resistance | 18 | 90 |
| Mediated Communication | Scheduling, Inference containment | 18 | 90 |
| Cross-Domain | Consensus, Inference containment | 18 | 90 |
| Multi-Party Group | Consensus, Coalition resistance | 18 | 90 |
| Hub-and-Spoke | Consensus, Coalition resistance | 18 | 90 |
| Competitive | Consensus, Coalition resistance | 18 | 90 |
| Affinity-Modulated | Scheduling, Inference containment | 18 | 90 |
| **Total** | 14 category/family cells | **126** | **630** |

If the pilot validates the difficulty tiers, the release grid expands the same layout to 210 main base tasks by increasing each category/family/tier cell from three base tasks to five. This produces 1050 main matched variants. The expansion is conditional, not part of the current paid gate run.

This layout supports matched comparisons such as `security - no_attacker` inside the same base task, rather than comparing unrelated tasks.

## 3. Scenario Bundle Contents

Each generated bundle contains the inputs needed to run one scenario:

```text
scenario.json
scenario.gt.json
docker-compose.yml
personas/<agent_id>.system.md
personas/<agent_id>.tools.json
mcp/<tool>.json
resources/
governance/manifest.json
```

`scenario.json` defines the social topology, agent IDs, task family, opening message, allowed tools, and turn cap.

`scenario.gt.json` defines the scoring target: terminal predicate, invariants, resource manifest, governance manifest, attack plan, tool manifest, phase schedule, attribution DAG inputs, and construction manifest.

`resources/` stores scenario-local filesystem and SQLite fixtures. These resources are mounted through audited `fs.*` and `db.*` tools, not directly exposed to agents as unaudited files.

`governance/manifest.json` records owners, identities, scopes, approval rules, and consent state used by governance attacks and scoring.

## 4. Construction Workflow

The current paid workflow is:

```text
select scaffold rows
  -> build skeleton payloads with scenario, GT, resources, and governance data
  -> run GPT-5 naturalization
  -> validate the naturalization patch
  -> materialize a bundle under benchmark/batches/<batch_id>/scenarios/<scenario_id>/
  -> run Docker Compose with one container per simulated user plus the gateway
  -> run GPT-4.1-mini agents through the audited gateway
  -> write logs, cassettes, resource-state evidence, and scorecards
  -> aggregate batch metrics and cost
  -> stop for review
```

For main matched variants, GPT-5 naturalizes the base task once and reuses the naturalized task context across the five attack modes. This keeps the five variants comparable. Hard-stratum rows are standalone tasks, so each hard row is naturalized separately.

Before GPT-5 naturalization, each base task should carry task schema v0. This schema records actors, visibility, initialization data/actions/message history, consensus or role rules, required evidence, evaluator bases, audit events, designed difficulty tier, and source-pattern metadata. tau2-bench contributes the contract pattern for setup, actions, assertions, and reward bases. WildClawBench contributes workspace and safety motifs such as filesystem preservation, secret leakage, semantic authority, prompt injection, unsafe operations, and draft-vs-send constraints. These sources are used as motifs only; generated benchmark rows synthesize new text, fixtures, profiles, and final-state predicates.

## 5. Simulation Artifacts

Each simulated scenario in `benchmark/batches/<batch_id>/scenarios/<scenario_id>/` has a copied bundle plus run outputs. The most useful files are:

| File | Purpose |
|---|---|
| `naturalization_patch.json` | GPT-5 naturalization output and token accounting. |
| `simulation_result.json` | Top-level pass/fail status, scorecard path, usage, and error string. |
| `bundle/run/simulation_report.json` | Conversation history, completion source, closure reason, and turn count. |
| `bundle/run/run_scorecard.json` | Task, privacy, security, governance, SAF, and diagnostic metrics. |
| `bundle/run/action_log.db` | Primary hash-chained action log. |
| `bundle/run/action_log.shadow.db` | Shadow log used for integrity checks. |
| `bundle/run/cassette.jsonl` | Replay data for LLM calls, tool calls, and policy decisions. |

The Docker run is accepted only if teardown completes and all required evidence exists for deterministic scoring.

## 6. Evaluation Metrics

The benchmark separates run readiness from measured outcomes.

`failed_count` in a batch report means readiness failure only. Examples include malformed bundles, Docker failure with no usable evidence, missing logs, evaluator crash, broken hash chains, or unscorable resource final state.

Accepted runs may still have negative outcomes. These are benchmark signals:

| Metric | Meaning |
|---|---|
| `task_success_count` | Number of accepted runs with TSR equal to 1.0. |
| `accepted_task_failure_count` | Accepted runs whose task failed but evidence is scoreable. |
| `attack_success_count` | Runs where the declared attack objective succeeded. |
| `attack_resisted_count` | Attack-mode runs where the attack objective did not succeed. |
| `privacy_attack_success_count` | Privacy invariant breach count. |
| `security_attack_success_count` | Security invariant breach count. |
| `governance_attack_success_count` | Governance invariant breach count. |
| `saf_failure_count` | Runs whose SAF score did not pass threshold. |
| `turn_cap_count` | Accepted runs that reached the hard turn cap. |
| `audit_summary` | Batch-level SAF overall mean/min, SAF pass rate, per-dimension means, and per-dimension failure counts. |
| `scenario_scorecard_digests` | Per-scenario review digest with scorecard path, task TSR, SAF scores, SAF passes, and privacy/security/governance indicators. |

Attack success is not the same as task failure. A privacy or governance attack can succeed while the social task still succeeds. A task can also fail without an attack succeeding.

## 7. Retained Batch Checkpoint

The old `batch-002x` smoke directories were debugging artifacts and are not retained. The retained paid runs are:

| Batch | Retained rows | Current use |
|---|---:|---|
| `batch-0061-resource-label-sanitized-25` | 25 | Diagnostic only. Metrics changed under corrected evaluator semantics. |
| `batch-0064-construction-metrics-fixes-50` | 50 | Diagnostic only. Metrics changed under corrected evaluator semantics. |
| `batch-0065-scale-gate-50-idx075` | 50 | Diagnostic only. Metrics changed under evaluator fixes and AM scheduling/naturalization construction fixes. |

Do not use these retained scorecards as final benchmark evidence. They remain useful for trajectory inspection and regression diagnosis.

The next paid checkpoint should rerun corrected replacement gates at scaffold indexes `0`, `25`, and `75`, stopping after each gate for review of generated task quality and simulation trajectories.

The retained runs match the planned replacement-gate index windows below. The table shows how task variants are distributed inside each batch. Attack modes are balanced within every complete base-task block: each listed base task contributes one `no_attacker`, one `collaboration`, one `security`, one `privacy`, and one `governance` variant.

| Retained batch / replacement gate | Index window | Variants | Base tasks | Category and family cells | Designed difficulty mix | Attack-mode mix |
|---|---:|---:|---:|---|---|---|
| `batch-0061-resource-label-sanitized-25` / rerun `start-index 0`, `batch-size 25` | 0-24 | 25 | 5 | Cross-User agent-to-agent Scheduling: 25 variants / 5 bases | easy: 15; realistic: 10 | 5 per mode |
| `batch-0064-construction-metrics-fixes-50` / rerun `start-index 25`, `batch-size 50` | 25-74 | 50 | 10 | Cross-User agent-to-agent Scheduling: 20 variants / 4 bases; Mediated Communication Scheduling: 30 variants / 6 bases | easy: 15; realistic: 20; stress: 15 | 10 per mode |
| `batch-0065-scale-gate-50-idx075` / rerun `start-index 75`, `batch-size 50` | 75-124 | 50 | 10 | Affinity-Modulated Scheduling: 35 variants / 7 bases; Mediated Communication Scheduling: 15 variants / 3 bases | easy: 15; realistic: 15; stress: 20 | 10 per mode |

## 8. Known Caveats

The retained checkpoint proves that the pipeline can generate, run, and score representative rows. It does not prove that the retained scorecards are release-ready, and it does not yet validate the 680-variant balanced difficulty pilot.

The hard-stratum rows currently pass task and readiness gates but fail SAF. The team should inspect whether this is expected weak auditability, missing hard-row SAF GT, or scorer calibration.

Episode graphs have not yet received a paid runtime smoke in the current checkpoint.

The five named audit challenge cases are scaffolded and validated structurally, but they still need hand review and paid runtime validation.

Human review is still required before any row is labeled `human_reviewed` or release-ready.

## 9. How To Inspect A Run

For a batch-level summary, open:

```text
benchmark/batches/<batch_id>/batch_report.json
```

For one scenario's trajectory, open:

```text
benchmark/batches/<batch_id>/scenarios/<scenario_id>/bundle/run/simulation_report.json
```

For metric details, open:

```text
benchmark/batches/<batch_id>/scenarios/<scenario_id>/bundle/run/run_scorecard.json
```

When reviewing a run, check these items in order:

1. `simulation_result.json.status` should be `simulation_passed` or another accepted status with a scoreable reason.
2. `simulation_report.json.done` should be true unless the run is an accepted turn-cap outcome.
3. `run_scorecard.json.task.tsr` explains task completion.
4. `run_scorecard.json.diagnostics.task_tool_evidence` shows whether required tool operations were observed.
5. Batch-level `attack_success_ids`, `saf_failure_ids`, and `accepted_task_failure_details` explain measured negative outcomes.

## 10. Recommended Next Step

Before full scale-out, rerun the corrected replacement gates from indexes `0`, `25`, and `75`. Review generated task quality and trajectories between gates. Only then continue toward the full 680-variant balanced difficulty pilot.
