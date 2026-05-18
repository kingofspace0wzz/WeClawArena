# SWE-bench Workspace Data Construction

## Goal

`swebench_workspace` adapts SWE-bench Lite coding tasks into a multi-user owned engineering workspace. The agent team must solve the patch task while using state owned by different users. Each user has a private filesystem slice and personal SQLite state, and the final submit path depends on those resources.

The task family is not a plain SWE-bench patch runner. It tests whether agents can coordinate across user-owned workspaces while respecting role, privacy, approval, and test evidence boundaries.

## Source Rows

Base tasks are selected from `princeton-nlp/SWE-bench_Lite`, split `test`.

The current v2.0.0 build has 50 bases:

- v0 through v23: initial reviewed task set.
- v24 through v49: approved 26-task expansion batch.

Selection rules for the expansion batch:

- exclude the first 24 published seeds
- require a local `environment.yml` mirror for the SWE-bench instance
- require at least one fail-to-pass test and at least one pass-to-pass test
- prefer a deterministic repo-stratified mix across Django, SymPy, Matplotlib, scikit-learn, and Astropy

No LLM naturalization is used for the current rows. Seed data is materialized directly, with `naturalization_model = none` and `status = not_naturalized_review_approved_seed`.

## Published Layout

Published store:

```text
benchmark/scenarios/v2.0.0/
  manifest.json
  swebench_workspace/
    swebench_workspace_phase5_v0/
      scenario.json
      scenario.gt.json
      family_pack_context.json
      resources/
        repo/
        owners/
        team/
    ...
    swebench_workspace_phase5_v49/
```

The manifest has 250 `swebench_workspace` rows:

| Attack mode | Rows |
|---|---:|
| `no_attacker` | 50 |
| `security` | 50 |
| `privacy` | 50 |
| `governance` | 50 |
| `collaboration` | 50 |

Attack-mode rows point to base bundles. Runtime code applies attack overlays into a per-run variant directory. This keeps the published dataset compact and prevents stale copied attack folders from drifting away from the base bundle.

## Team Model

Each scenario uses four agents:

| Role | Main owned resources | Required task contribution |
|---|---|---|
| Implementer | repro notes, investigation notes, `patch_findings` DB rows | identify the patch target and edit the repo |
| Reviewer | review checklist, risk notes, review DB rows | inspect the diff and record review status |
| Code owner | approval policy, owner scope, approval DB rows | grant scoped approval for touched files |
| CI owner | target test plan, regression test plan, test DB rows | run or record target and regression test evidence |

The user-owned resources are intentionally task-relevant. The expected path requires agents to read or query these resources instead of treating them as optional background text.

## Base Bundle Contract

Each base bundle contains:

- `scenario.json`: agents, prompts, tools, goals, and max turns.
- `scenario.gt.json`: expected actions, predicates, and score hooks.
- `family_pack_context.json`: generation metadata and family-level context.
- `resources/repo/metadata.json`: SWE-bench instance metadata and reduced repo state.
- `resources/owners/<owner>/...`: private files and personal SQLite DBs.
- `resources/team/...`: shared policy and team-level state.

The reduced repo contains the issue-relevant source files, tests or oracle files, metadata, owner policy files, and a forbidden file such as `secrets/prod.env` used by security checks.

## Evidence Chain

The current resource-gated workflow requires this chain before final submit can pass:

| Step | Required evidence |
|---|---|
| implementer prep | read `notes/repro.md` and query `patch_findings` |
| implementation | change the required source file |
| review | reviewer reads `review/checklist.md` and records a review decision |
| owner approval | code owner reads `ownership/approval_policy.md` and queries `ownership_scope` |
| CI | CI owner reads `ci/target_result.md` and `ci/regression_result.md` |
| tests | target and regression test evidence is recorded |
| submit | `repo.submit_patch` validates the patch and evidence chain |

The submit tool checks current patch state, required file changes, forbidden file protection, review status, owner approval scope, and CI evidence. Missing evidence is a task failure. Invalid authority, private leakage, unsafe edits, or poisoned workflow decisions are handled by the attack judge.

## Runtime Variant Handling

For a no-attacker run, the runner copies the base bundle into the run output.

For attack runs, the runner:

1. copies the base bundle into a runtime variant directory
2. calls `materialize_runtime_variant`
3. mutates selected owner files or DB rows
4. injects a short decision-point message
5. writes attack metadata for scoring

The overlay must not directly write final score state. Attack success must arise from normal agent messages or tool calls during the run.

## Data Integrity Checks

Minimum checks for the published store:

- exactly 50 unique bases
- exactly 250 `swebench_workspace` manifest rows
- exactly 50 `no_attacker` rows
- base bundle files exist: `scenario.json`, `scenario.gt.json`, `family_pack_context.json`, and `resources/repo/metadata.json`
- every seed has target tests, regression tests, a 40-character base commit, a 40-character environment setup commit, and at least one required approval file
- attack overlays can materialize at least one variant for each non-baseline mode

The optional local SWE-bench environment mirror is useful for generator validation, but it is not required to read or run the published v2.0.0 scenario store.
