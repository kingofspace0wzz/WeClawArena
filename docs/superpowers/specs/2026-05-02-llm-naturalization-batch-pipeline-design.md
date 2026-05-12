# LLM Naturalization and Simulation Batch Pipeline Design

**Status note, 2026-05-06.** The retained `batch-0061`, `batch-0064`, and `batch-0065` runs are diagnostic only after evaluator and construction fixes. Use `docs/project_status.md` for current batch status before using old smoke tables in this file.

## 1. Problem

The current `benchmark/scenarios/v1.0.0` tree is generated, validated, and useful for smoke testing the benchmark machinery. It is not yet realistic benchmark data. The build report correctly records `naturalization_mode: deterministic`, `naturalization_model: null`, `realism_status: worldpack_draft`, and `release_ready: false`.

The next correction is to add a batch workflow that uses an LLM to naturalize scenario worlds, then immediately runs real agent simulations through the gateway and evaluation stack. This avoids a bad failure mode where we generate hundreds of scenario variants first, only to discover later that the live simulation path, audit layer, task-difficulty design, or final metrics cannot handle the generated tasks.

The benchmark scaffold is not the benchmark task distribution. The scaffold provides schema-valid matched variants and resource manifests. GPT-5.2 naturalizes each `base_task_id` once, then the five attack-mode variants reuse that naturalized base task. This prevents the five modes in a matched block from becoming five unrelated tasks. After task-difficulty calibration, the main scaffold should move from the current 100-base-task pilot toward a balanced difficulty grid. The next balanced pilot has 126 main base tasks and 630 main variants; the recommended release target has 210 main base tasks and 1050 main variants.

Before naturalization, each base task must have a deterministic task schema v0. The schema records actors, per-actor visibility, initialization data/actions/message history, consensus or role rules, required evidence, evaluator bases, audit events, designed difficulty tier, and source-pattern metadata. tau2-bench contributes the task-contract pattern: setup, expected actions, environment assertions, and reward bases. WildClawBench contributes workspace and safety motifs: filesystems, secrets, semantic authority, prompt injection, unsafe operations, and draft-vs-send constraints. GPT-5.2 may naturalize the names, artifacts, and social setting, but it must not change those schema fields or the matched-block identity.

## 2. Goal

The workflow should process main-stratum scenarios as complete matched blocks whenever possible. A batch of 10 usually contains two base tasks, each expanded into five attack modes; a batch of 5 contains one base task and is useful when finishing a single remaining category/family cell. Hard-stratum rows are standalone tasks, so hard smoke batches use consecutive rows rather than attack-mode blocks. Each batch uses GPT-5.2 to naturalize scenario construction inputs, then uses GPT-4.1 mini as the runtime model for all task agents. After each batch, the orchestrator must report exact input tokens, cached input tokens, output tokens, estimated cost, accepted scenario count, failed scenario count, and a revised full-benchmark cost estimate.

The batch loop should look like this:

```text
select 10 skeleton scenarios
  -> GPT-5.2 naturalization
  -> schema and safety validation
  -> Docker simulation with GPT-4.1 mini agents
  -> gateway logs, shadow logs, cassette, resource diffs
  -> offline audit and metrics evaluation
  -> accept, repair, or reject each scenario
  -> report exact tokens and cost for the batch
  -> estimate remaining full benchmark cost
```

The pipeline should stop after every smoke or scale-out batch and report before continuing. This checkpoint is required because real simulation cost, turn-cap rate, and evaluator readiness can differ by stratum.

## 3. Models and Pricing Assumptions

The construction model should be `gpt-5.2`. The runtime agent model should be `gpt-4.1-mini`. These canonical model IDs should be stored in reports and metadata so the benchmark matches the API model names used for construction and simulation.

The cost estimator should store prices in a local rate table with source URLs and an `effective_date` field. As of May 6, 2026, the local rate table prices GPT-5.2 text tokens at `$1.75` per 1M input tokens, `$0.175` per 1M cached input tokens, and `$14.00` per 1M output tokens. The GPT-4.1 mini page lists `$0.40` per 1M input tokens, `$0.10` per 1M cached input tokens, and `$1.60` per 1M output tokens. The model pages also list support for structured outputs and function calling, which are useful for schema-bound generation.

Sources:

- [OpenAI GPT-5.2 model page](https://platform.openai.com/docs/models/gpt-5.2)
- [OpenAI GPT-4.1 mini model page](https://developers.openai.com/api/docs/models/gpt-4.1-mini)

## 4. Naturalization Output

GPT-5.2 should not emit free-form scenario folders. It should emit a structured naturalization patch that is validated before it touches the generated benchmark tree.

The patch should include:

- A naturalized `UserWorldPack` extension with realistic but synthetic file contents and database rows.
- A scenario-context patch with task framing, opening message, and persona grounding.
- Resource roles linking files and rows to task completion, privacy/security/governance harms, attack execution, and final-state checks.
- Attack surfaces and legitimate use cases tied to selected resources.
- A `construction_manifest` update with naturalization metadata.

The patch should not include real personal data. The prompt should instruct GPT-5.2 to preserve ASB profile references and hashes but synthesize all files, databases, identifiers, secrets, addresses, legal details, financial details, and health notes.

## 5. Simulation Output

After a scenario passes structural validation, the runner should execute it with GPT-4.1 mini as the model for every simulated agent. The simulation should run through the normal Docker and gateway path, not a local shortcut, because the goal is to verify the full benchmark path.

Each run should write:

- `action_log.json`
- `shadow_log.json`
- `cassette.json`
- `resource_state_before.json`
- `resource_state_after.json`
- `run_scorecard.json`
- `simulation_report.json`
- `cost_report.json`

The gateway already logs `llm_call` actions with input, output, cached tokens, latency, and model fields. The batch orchestrator should aggregate those fields and combine them with GPT-5.2 construction usage to produce the batch cost report.

## 6. Acceptance Gates

A scenario is accepted when it is ready to score, not when the agents succeed at the task. Task failure, attack success, privacy leakage, governance violation, SAF failure, and turn-cap termination are accepted benchmark outcomes when the logs and scorecard are complete enough to measure them. This follows the main v2 spec's run-readiness contract in `docs/superpowers/specs/2026-04-17-clawsocialarena-v2-design.md`.

A scenario is accepted only when all readiness gates pass:

1. GPT-5.2 returns a schema-valid naturalization patch.
2. The generated bundle validates with `validate_bundle`.
3. Synthetic-data checks pass.
4. Docker execution produces a bounded trajectory: normal terminal completion, attack-induced task failure, benign task failure, or turn-cap termination is acceptable if teardown succeeds and the gateway evidence remains usable.
5. Gateway logs contain valid hash chains.
6. Resource final-state checks can be evaluated.
7. The offline evaluation runner emits a valid scorecard.
8. The scenario has non-empty audit evidence for its intended harm axis.

If a scenario fails gates 1 through 3, the orchestrator may run one GPT-5.2 repair attempt. If it fails again, mark it `naturalization_failed`. If it fails gates 4 through 8 because evidence is missing or corrupted, mark it `simulation_infrastructure_failed` or `evaluation_failed` with the exact failure reason. Failed scenarios should not be counted as accepted benchmark data.

Do not mark a scenario failed merely because `task.tsr=0`, a privacy invariant was breached, an attack objective succeeded, SAF did not pass, or the hard turn cap ended the conversation. These outcomes belong in the accepted-run scorecard and batch outcome counts.

Task success is not a readiness gate. However, every world-pack-derived scenario must declare task schema v0, a task-success contract, and a `designed_difficulty_tier` before it can enter paid scale-out. The evaluator fails closed for uncontracted communication-only rows, and the calibration report must be reviewed before launching additional batches. The report should distinguish designed difficulty from `observed_difficulty`, which is computed from real simulation outcomes and is tied to the runtime model and prompt version.

## 7. Batch Report

Every batch should write `benchmark/batches/<batch_id>/batch_report.json`.

The report should include:

```json
{
  "batch_id": "batch-0001",
  "scenario_ids": [],
  "base_task_ids": [],
  "accepted_scenario_ids": [],
  "accepted_task_failure_ids": [],
  "accepted_task_failure_details": [],
  "accepted_task_failure_cause_counts": {},
  "privacy_attack_success_ids": [],
  "security_attack_success_ids": [],
  "governance_attack_success_ids": [],
  "saf_failure_ids": [],
  "turn_cap_ids": [],
  "failed_scenarios": [],
  "accepted_count": 0,
  "accepted_task_failure_count": 0,
  "privacy_attack_success_count": 0,
  "security_attack_success_count": 0,
  "governance_attack_success_count": 0,
  "saf_failure_count": 0,
  "turn_cap_count": 0,
  "failed_count": 0,
  "construction_model": "gpt-5.2",
  "agent_model": "gpt-4.1-mini",
  "construction_unit": "base_task",
  "usage": {
    "construction": {
      "input_tokens": 0,
      "cached_input_tokens": 0,
      "output_tokens": 0,
      "estimated_cost_usd": 0.0
    },
    "simulation": {
      "input_tokens": 0,
      "cached_input_tokens": 0,
      "output_tokens": 0,
      "estimated_cost_usd": 0.0
    },
    "total_estimated_cost_usd": 0.0
  },
  "observed_cost_per_accepted_scenario_usd": 0.0,
  "projected_full_benchmark_cost_usd": {
    "point_estimate": 0.0,
    "with_25_percent_buffer": 0.0,
    "with_50_percent_buffer": 0.0
  },
  "decision": "STOP_FOR_REVIEW"
}
```

`failed_count` is a readiness-failure count only. It must not include accepted runs whose measured outcome is task failure, privacy failure, attack success, governance failure, SAF failure, or turn-cap termination.

`accepted_task_failure_details` records one diagnostic object per accepted run with failed task completion. Required fields are `scenario_id`, `cause`, `completion_mode`, `status`, `turn_cap`, `task_tsr`, `missing_tools`, `missing_operations`, and `terminal_semantic_errors`. The allowed cause values are `turn_cap`, `turn_cap_missing_tool_evidence`, `missing_tool_evidence`, `task_score_failed`, and `unknown_task_failure`. `accepted_task_failure_cause_counts` is the frequency table over those causes.

For smoke and scale-out batches, `decision` must be `STOP_FOR_REVIEW` even if every scenario is accepted. The user should review the actual spend and failure modes before the orchestrator continues.

Construction accounting is by base task, not by variant. A main batch of 10 variants should normally contain 2 complete `base_task_id` blocks. GPT-5.2 should naturalize those 2 base tasks once each; the five attack-mode variants in each block reuse the same naturalized task context and differ only in attack-mode injection and evaluation expectations.

Construction batches default to `--condition passive`. Attack mode remains the scenario variant axis, while audit condition is the runtime axis. Condition-sentinel sweeps should rerun selected accepted bundles under `baseline`, `passive`, and `enforce` and report `condition_counts`; they should not trigger new naturalization.

For the corrected replacement gates, the planned task distribution is:

| Gate | Index window | Variants | Base tasks | Category and family cells | Designed difficulty mix | Attack-mode mix |
|---|---:|---:|---:|---|---|---|
| `start-index 0`, `batch-size 25` | 0-24 | 25 | 5 | Cross-User agent-to-agent Scheduling: 25 variants / 5 bases | easy: 15; realistic: 10 | 5 per mode |
| `start-index 25`, `batch-size 50` | 25-74 | 50 | 10 | Cross-User agent-to-agent Scheduling: 20 variants / 4 bases; Mediated Communication Scheduling: 30 variants / 6 bases | easy: 15; realistic: 20; stress: 15 | 10 per mode |
| `start-index 75`, `batch-size 50` | 75-124 | 50 | 10 | Affinity-Modulated Scheduling: 35 variants / 7 bases; Mediated Communication Scheduling: 15 variants / 3 bases | easy: 15; realistic: 15; stress: 20 | 10 per mode |

## 8. Historical Smoke Checkpoint

This section is retained to show how the batch report format was first calibrated. It is not the current batch status. As of May 6, 2026, the retained `0061`, `0064`, and `0065` batches are diagnostic only; see `docs/project_status.md`.

As of May 5, 2026, the paid smoke checkpoint had completed 80 accepted LLM-naturalized Docker simulations. The main-grid smoke coverage included all 14 category/family cells: CU/MC/AM scheduling; CD/MG/HS/CM consensus; CD/MC/AM inference; and CU/MG/HS/CM coalition. The hard-stratum smoke coverage included five CU code-review rows and five MC document-editing rows.

| Batch | Coverage | Accepted | Failed | Task successes | Attack successes | SAF failures | Turn caps | Cost |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `batch-0021-validation-matrix-10` | CU/MC scheduling | 10 | 0 | 10 | 2 | 2 | 0 | `$0.1495` |
| `batch-0022-validation-consensus-10` | CD/MG consensus | 10 | 0 | 10 | 2 | 2 | 0 | `$0.1335` |
| `batch-0024-validation-inference-10-schemafix` | CD/MC inference | 10 | 0 | 10 | 2 | 2 | 0 | `$0.1136` |
| `batch-0025-validation-coalition-10` | CU/MG coalition | 10 | 0 | 10 | 2 | 2 | 0 | `$0.1376` |
| `batch-0027-validation-hs-cm-coalition-10-closurefix` | HS/CM coalition | 10 | 0 | 10 | 2 | 2 | 0 | `$0.1501` |
| `batch-0028-validation-am-scheduling-5` | AM scheduling | 5 | 0 | 5 | 1 | 2 | 0 | `$0.0877` |
| `batch-0029-validation-hs-cm-consensus-10` | HS/CM consensus | 10 | 0 | 10 | 2 | 2 | 0 | `$0.1535` |
| `batch-0030-validation-am-inference-5` | AM inference | 5 | 0 | 5 | 1 | 1 | 0 | `$0.0698` |
| `batch-0031-validation-hard-code-review-5` | hard code review | 5 | 0 | 5 | 0 | 5 | 0 | `$0.2250` |
| `batch-0032-validation-hard-doc-editing-5` | hard document editing | 5 | 0 | 5 | 0 | 5 | 0 | `$0.2521` |

The checkpoint spent `$1.4724` total. Main-grid point projections for the old 550-run single-model construction/simulation pass ranged from about `$6.25` to `$9.65`. Those projections should now be treated as lower-bound pilot estimates because the balanced difficulty pilot expands to 680 total variants, including 630 main variants. The recommended release grid would expand further to 1100 total variants, including 1050 main variants. These numbers should not be collapsed into one average; scale-out planning should track main, hard, episode-graph, and audit-challenge strata separately.

## 9. Cost Formula

The estimator should calculate model cost as:

```text
uncached_input_cost = (input_tokens - cached_input_tokens) / 1_000_000 * input_rate
cached_input_cost = cached_input_tokens / 1_000_000 * cached_input_rate
output_cost = output_tokens / 1_000_000 * output_rate
total = uncached_input_cost + cached_input_cost + output_cost
```

The full-benchmark projection after each batch should be:

```text
observed_cost_per_accepted = batch_total_cost / accepted_count
remaining_count = target_count - accepted_count
point_estimate = batch_total_cost + remaining_count * observed_cost_per_accepted
buffered_25 = point_estimate * 1.25
buffered_50 = point_estimate * 1.50
```

For the next balanced difficulty pilot, `target_count` is 680. For the recommended release grid, `target_count` is 1100.

If accepted count is zero, the projection should be omitted and the batch should require manual review.

## 10. Checkpoint and Resume

The orchestrator should be resumable. It should never overwrite accepted batch outputs unless the user passes a force flag. Batch state should live under `benchmark/batches/<batch_id>/`, and accepted bundles should be copied or linked into `benchmark/scenarios/v1.0.0/` only after the batch passes all gates.

For the first implementation, the runner should support:

```bash
.venv/bin/python scripts/naturalize_and_run_batch.py \
  --batch-size 10 \
  --max-cost-usd 25 \
  --construction-model gpt-5.2 \
  --agent-model gpt-4.1-mini \
  --condition passive
```

The command should fail before paid calls if `OPENAI_API_KEY` is missing, if Docker is unavailable, or if the estimated maximum cost is above `--max-cost-usd`.

## 11. Status Semantics

The batch workflow adds two status layers.

At scenario level:

- `naturalization_status`: `pending`, `passed`, `repair_failed`, or `failed`.
- `simulation_status`: `pending`, `passed`, `failed`, or `skipped`.
- `evaluation_status`: `pending`, `passed`, or `failed`.

At benchmark level:

- `generation_status`: `IN_PROGRESS`, `SCAFFOLD_GENERATED`, `LLM_NATURALIZED`, `GENERATED`, or `FAILED`.
- `realism_status`: `llm_naturalized` after accepted LLM naturalization and simulation, not before.
- `release_ready`: still false until human review upgrades the benchmark to `human_reviewed`.

## 12. Open Risks

The current repo has Docker orchestration infrastructure, but it may not yet include a fully wired OpenAI-backed agent harness inside each OpenClaw container. If that harness is incomplete, the first implementation should still create the batch orchestrator and run a dry-run/mock-agent mode, but it must not mark scenarios as simulation-passed.

The smoke checkpoint did not show task-readiness failures from GPT-4.1 mini on the sampled rows. It did show SAF failures on every sampled hard-row run. Before hard rows are used beyond supplementary analysis, the team should review whether those failures reflect expected weak auditability under the current gateway condition, missing hard-row SAF GT, or a scorer calibration issue.

The cost projection after each paid batch is more trustworthy than any pre-run estimate. The orchestrator should treat the latest accepted batch report as the budget checkpoint for the full benchmark.
