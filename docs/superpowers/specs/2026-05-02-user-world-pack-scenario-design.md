# User World Pack Scenario Construction Design

## 1. Problem

The current benchmark scaffold path is structurally useful but not yet a realistic benchmark construction process. `scripts/generate_benchmark_scaffold.py` can produce 550 valid pre-calibration scenario variants, and every non-audit variant can carry scenario-local world-pack resources. However, those resources remain scaffold inputs for LLM naturalization, not final tasks. They are not yet LLM-naturalized or human-reviewed, and they still need stronger evidence that each file or database row exists for a realistic reason tied to the task, policy, attack surface, final-state check, and designed difficulty tier.

That distinction matters for the benchmark claim. A valid bundle proves schema, routing, scoring, and orchestration coverage. It does not prove that the task setup is realistic enough to test agent behavior in a simulated social network. The benchmark should not call generated data final unless each task, user context, private resource, policy, attack surface, and expected final state comes from a coherent user-world model.

## 2. Goal

The corrected design makes the user world pack the base unit of scenario construction. A scenario should be derived from one or more world packs, not patched with standalone resources afterward. The world pack starts from AgentSocialBench user profiles and privacy-boundary declarations, then extends them with synthetic filesystem state, personal databases, policies, sensitive items, ordinary work patterns, and likely attack surfaces. Scenario generation then selects a task family and harm category, chooses compatible world packs, selects resources with explicit roles, and builds the task, attack plan, manifests, and expected final state from that selected world.

The immediate goal is not to build a full operating-system image for every user. The immediate goal is to create portable scenario-local resource subsets that are grounded in richer reusable world packs. Containerized users can still mount scenario resources, but the source of those resources is a world pack, and the scenario bundle records that source.

## 3. Non-Goals

The first implementation should not mount a full home directory into every user container. Scenario bundles should remain portable and reviewable. Each bundle should include only the files, directories, and databases needed for the task, attack, and evaluation.

The benchmark must not contain real personal data. All files, database rows, names, identifiers, and secrets must be synthetic. If LLM generation is used for natural language realism, the build report must record the model and prompt/cache hashes, and the output must still pass the same synthetic-data checks.

This design does not replace the gateway policy hook, SAF scoring, MSWM, or resource-governance design. It changes how scenarios and resources are constructed so those systems have realistic inputs to audit.

## 4. AgentSocialBench Profile Source

AgentSocialBench should be the required profile source for normal benchmark users. A world pack should not invent a persona from scratch unless it is an explicitly marked synthetic audit challenge. For normal scenarios, the construction path is:

```text
AgentSocialBench profile + privacy-boundary declaration
  -> UserWorldPack user profile, relationships, and policy seed
  -> synthetic filesystem and personal database resources
  -> scenario-local resources, manifests, attacks, and expected final state
```

The `asb://profiles/...` reference should therefore become a resolved input, not just a string in `persona_manifest`. Prior work already added a `ProfileBank` loader under `worktree/phase-I-governance/clawsocialarena/generator/profiles.py` for AgentSocialBench-shaped profile JSON. The active implementation should port that loader into the root package, not create an unrelated second loader. The port should extend `ProfileBank` so it records the AgentSocialBench dataset version, profile reference, profile hash, source path, and privacy-boundary references used to build each user. The world pack may adapt the profile into a shorter persona prompt for OpenClaw, but it must keep the original `profile_source.profile_ref` and `profile_source.profile_hash` so downstream reports can verify which AgentSocialBench profile was used.

Filesystem and database resources are synthetic extensions of the AgentSocialBench profile. AgentSocialBench supplies the social role, relationship structure, preferences, and privacy boundaries. The world-pack generator supplies realistic but synthetic files, SQLite rows, consent scopes, and attack surfaces that are consistent with that profile. This avoids claiming that AgentSocialBench already contains per-user files or databases unless the actual dataset version does.

## 5. Core Abstraction

The new base object is `UserWorldPack`.

```json
{
  "world_id": "world-travel-clinic-001",
  "schema_version": "world-pack-v1",
  "users": [
    {
      "user_id": "user-alex",
      "profile_source": {
        "dataset": "AgentSocialBench",
        "dataset_version": "asb-v1",
        "profile_ref": "asb://profiles/travel-clinic/alex",
        "profile_hash": "sha256:example",
        "privacy_boundary_refs": [
          "asb://privacy_boundaries/travel-clinic/alex"
        ]
      },
      "persona": {
        "display_name": "Alex Rivera",
        "role": "graduate student",
        "goals": ["book visa appointment", "coordinate lab travel"],
        "risk_tolerance": "low"
      },
      "relationships": [
        {
          "other_user_id": "user-sam",
          "relationship": "lab coordinator",
          "trust_level": "medium"
        }
      ]
    }
  ],
  "resources": {
    "files": [],
    "databases": []
  },
  "policies": {},
  "sensitive_items": [],
  "legitimate_use_cases": [],
  "attack_surfaces": []
}
```

A file entry records path, owner, sensitivity, semantic tags, allowed operations, content source, expected task role, and expected final state. A database entry records path, tables, rows or row generators, row filters, owner, sensitivity, consent rules, and expected read/write/delete behavior. Sensitive items are not just strings to scan for. They are linked to owners, resources, policies, and expected harm categories.

Every resource included in a scenario must have one or more roles:

- `task_relevant`: needed to complete the benign task.
- `privacy_sensitive`: protected item that should not be revealed or copied without authorization.
- `governance_bound`: access depends on owner, identity, scope, or approval state.
- `attack_target`: the attacker has an explicit reason to read, alter, delete, or infer it.
- `audit_evidence`: final state or logs should prove whether access or mutation occurred.

Resources without roles should not be copied into scenario bundles.

## 6. Scenario Construction Flow

Scenario construction should follow this sequence.

1. Select a benchmark cell: stratum, category, task family, harm axis, and attack family.
2. Resolve compatible AgentSocialBench profiles and privacy-boundary declarations.
3. Select one or more compatible world packs built from those AgentSocialBench profile sources.
4. Select a legitimate user goal from the world pack, then phrase the benchmark opening task around that goal.
5. Select only the resources needed for task completion, attack execution, policy checks, and final-state evaluation.
6. Build `persona_manifest`, `resource_manifest`, and `governance_manifest` from the world pack and its AgentSocialBench source metadata, not from generic overlays.
7. Build the task template shape, attack plan, injected actions, terminal predicate, invariants, and expected final resource state from the selected resources.
8. Copy scenario-local resource fixtures into the bundle under `resources/users/<user_id>/...`.
9. Record a construction manifest in the GT bundle and build report.
10. Validate schema, AgentSocialBench source references, resource roles, policy references, synthetic-data checks, and final-state expectations.
11. Mark the benchmark realism status based on the strictest completed review level.

The existing deterministic templates can still be used as skeletons, but the skeleton should be filled from selected world packs rather than from fixed profile strings or resource overlays.

## 7. Filesystem and Database Layout

World packs should live outside individual scenario bundles:

```text
benchmark/worlds/v1.0.0/
  world-travel-clinic-001/
    world.json
    filesystem/
      users/user-alex/home/notes/visa.md
      users/user-alex/home/lab/travel-budget.csv
    databases/
      users/user-alex/personal.sqlite
```

Scenario bundles should copy only the selected subset:

```text
benchmark/scenarios/v1.0.0/main/MC/scheduling/MC_SCHED_001/
  scenario.json
  scenario.gt.json
  resources/
    users/user-alex/files/home/notes/visa.md
    users/user-alex/db/personal.sqlite
  manifests/
    resource_manifest.json
    governance_manifest.json
```

Containers should see the scenario-local `resources/` tree, not the entire world-pack store. This keeps each scenario portable and makes resource diffs easy to audit. A later execution layer can mount those resources into each user's container, but the benchmark data should stay scenario-local.

SQLite databases should be generated from world-pack table specs. This avoids hand-editing binary database files as the source of truth. The generated database file is part of the scenario bundle, and the world pack records the table definitions and seed rows that produced it.

## 8. Construction Manifest

Every generated scenario should include a construction manifest in `scenario.gt.json`. The manifest records how the scenario was built and whether it can be treated as release-ready.

```json
{
  "construction_manifest": {
    "construction_mode": "world_pack",
    "world_pack_schema_version": "world-pack-v1",
    "world_pack_ids": ["world-travel-clinic-001"],
    "profile_sources": [
      {
        "user_id": "user-alex",
        "agent_id": "agent-alex",
        "dataset": "AgentSocialBench",
        "dataset_version": "asb-v1",
        "profile_ref": "asb://profiles/travel-clinic/alex",
        "profile_hash": "sha256:example"
      }
    ],
    "selected_resource_ids": [
      "file-alex-visa-notes",
      "db-alex-personal-health"
    ],
    "naturalization": {
      "mode": "deterministic",
      "provider": null,
      "model": null,
      "prompt_hash": null,
      "cache_key": null
    },
    "realism_status": "worldpack_draft"
  }
}
```

If an LLM is used to naturalize task text, file content, messages, or social details, the manifest must record provider, model, prompt hash, cache key, and generation date. If no LLM is used, the manifest must say `mode: deterministic`. The orchestration report must not leave the construction mode implicit.

## 9. Realism Status Levels

The benchmark should use explicit realism status values.

- `structural_draft`: schema-valid deterministic scaffold. Useful for tests, not a final benchmark.
- `worldpack_draft`: scenarios derive from world packs and resource roles, but have not passed review.
- `llm_naturalized`: world-pack-derived scenarios have LLM-generated or LLM-refined natural language, with model metadata recorded.
- `human_reviewed`: sampled and corrected by human review, with review notes attached.

Only `human_reviewed` should be described as final benchmark data. A fully generated `v1.0.0` directory that remains `structural_draft` or `worldpack_draft` is generated, but it is not ready for release claims.

## 10. Attack Vectors Enabled by World Packs

World packs make more attack vectors realistic because the resource state has meaning before the task starts. The benchmark can test unauthorized disclosure, cross-user exfiltration, policy-bypassing database reads, unauthorized writes, file deletion, destructive edits, silent copying, stale consent, identity confusion, and inference from partial private state.

For filesystem resources, attack vectors should include reading private files, writing misleading content, deleting files without consent, copying protected files to another user workspace, and using file metadata to infer sensitive facts. For database resources, attack vectors should include querying restricted rows, updating protected rows, deleting records, joining tables to infer hidden attributes, and using allowed aggregate access to recover row-level details.

Each attack vector should map to one or more harm categories and one or more SAF/audit checks. If no check can observe a harm, the construction system should either add the needed audit evidence or mark the scenario out of scope.

## 11. Orchestration Gate

The benchmark orchestrator should report both generation status and realism status. `GENERATED` should mean files were written. It should not mean release-ready. The report should include:

- `generation_status`: `READY_TO_GENERATE`, `SCAFFOLD_GENERATED`, `LLM_NATURALIZED`, `GENERATED`, or `FAILED`.
- `construction_mode`: `template_overlay`, `world_pack`, or `mixed`.
- `profile_source`: `agentsocialbench`, `synthetic_audit_challenge`, or `mixed`.
- `asb_dataset_version`: AgentSocialBench dataset version when applicable.
- `naturalization_mode`: `deterministic`, `llm`, or `hybrid`.
- `naturalization_model`: model identifier when applicable.
- `realism_status`: one of the status levels above.
- `release_ready`: true only when schema validation, test gates, resource-role checks, and review gates all pass.

Scaffold bundles should be reported as `SCAFFOLD_GENERATED`, not as final benchmark tasks. This is not a failure of the materializer. It is a correction to the claim attached to that output: deterministic world-pack bundles are inputs to naturalization and simulation, not release-ready benchmark data.

## 12. Acceptance Criteria

The corrected design is complete when every benchmark scenario records its AgentSocialBench profile sources, world-pack source, selected resources, construction mode, naturalization metadata, resource roles, policy references, and realism status.

Every selected file or database row must have a reason to exist in the scenario. The reason must connect to task completion, privacy/security harm, governance, attack execution, or final-state evaluation.

The orchestrator must prevent a deterministic scaffold from being labeled final. It can still generate and validate structural drafts, but release-ready benchmark data requires world-pack construction and review.

## 13. Implications for Current Data

The current 550-variant generated data should be treated as a world-pack draft and smoke-test corpus. It is useful for exercising schema, manifests, orchestration, resources, and scoring paths. It should not be presented as the final realistic benchmark until LLM naturalization, task-success calibration, designed difficulty calibration, and human review advance its `realism_status`. The next planned scaffold is a 680-variant balanced difficulty pilot. If that pilot shows useful separation between `designed_difficulty_tier` and `observed_difficulty`, the recommended release grid expands to 1100 total variants with 1050 main variants.

World-pack construction should feed task schema v0, not just resource manifests. The schema should connect each file, database row, and message fixture to actors, visibility, initialization data/actions/message history, consensus or role rules, required evidence, evaluator bases, audit events, and source-pattern metadata. tau2-bench-style task contracts provide the setup/action/assertion shape; WildClawBench-style workspace tasks provide resource motifs such as protected files, secrets, stale records, prompt-injected documents, and authority labels. The benchmark should synthesize new fixture content from those motifs rather than copying external tasks directly.

The current `persona_manifest` entries that look like `asb://profiles/...` should be treated as unresolved references unless the build report proves that `ProfileBank` resolved them from the AgentSocialBench profile directory. The active smoke batches now demonstrate the next layer: GPT-5 naturalization patches record profile source metadata, resource source metadata, prompt hashes, cache keys, and `realism_status: llm_naturalized` inside the per-run bundles under `benchmark/batches/`. These batch outputs are candidate benchmark data for review, not yet release-ready corpus data.

As of May 5, 2026, the smoke checkpoint has 80 accepted paid runs with zero readiness failures and zero turn caps. The main-grid smoke set covers all 14 category/family cells. The hard smoke set covers five code-review and five document-editing rows, and all sampled hard rows currently fail SAF while still passing task and readiness gates. That pattern should be treated as evidence for hard-stratum audit calibration, not as proof that the world-pack construction path is invalid.

The next implementation should port and extend the existing `ProfileBank`, build the world-pack schema and seed corpus, then switch scenario construction from resource overlays to world-pack selection. The current LLM-naturalized smoke data should guide this work: every selected resource must remain tied to task completion, privacy/security harm, governance checks, attack execution, or final-state evaluation, and the final release should not be claimed until human review upgrades the relevant rows to `human_reviewed`.
