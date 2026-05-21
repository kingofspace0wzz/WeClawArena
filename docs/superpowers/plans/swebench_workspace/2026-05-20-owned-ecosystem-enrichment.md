# SWE-bench Workspace Owned Ecosystem Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `swebench_workspace` owner files and DBs scenario-specific, resource-critical, and verifiable before the next no-attacker sweep.

**Architecture:** Add a structured resource-fact contract to the v2 evidence bundle, materialize each fact into owner files and SQLite `resource_facts` rows, then keep the existing v2 evidence-chain gates as the utility dependency. Regenerate the published 50 base bundles and stop before simulation.

**Tech Stack:** Python dataclasses, SQLite, existing SWE-bench workspace family pack materializer, pytest.

---

### Task 1: Resource Fact Contract

**Files:**
- Modify: `clawsocialarena/generator/family_packs/swebench_workspace/v2_schema.py`
- Test: `tests/test_generator/test_swebench_workspace_v2_schema.py`

- [ ] **Step 1: Add failing assertions for resource facts**

Update `test_v2_evidence_bundle_has_four_owned_ecosystems` to assert:

```python
maya = evidence.owner_specs["maya"]
opal = evidence.owner_specs["opal"]
assert "resource_facts" in maya.sqlite_tables
assert len(maya.sqlite_tables["resource_facts"]) >= 5
assert any(
    row["fact_id"] == "implementer.required_file"
    and row["fact_value"] == bundle.required_approval_files[0]
    for row in maya.sqlite_tables["resource_facts"]
)
assert any(
    row["fact_id"] == "code_owner.constraint_id"
    and row["fact_value"] == bundle.owner_constraint_id
    for row in opal.sqlite_tables["resource_facts"]
)
assert bundle.instance_id in maya.files["notes/repro.md"]
assert bundle.required_approval_files[0] in maya.files["notes/patch.md"]
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
pytest tests/test_generator/test_swebench_workspace_v2_schema.py -q
```

Expected: fail because `resource_facts` is not present.

- [ ] **Step 3: Add `ResourceFact` and richer role resources**

In `v2_schema.py`, add:

```python
@dataclass(frozen=True)
class ResourceFact:
    fact_id: str
    owner_id: str
    role: str
    location: str
    required_for: str
    privacy: str
    attack_surface: str
    fact_value: str
```

Extend `OwnerEvidenceSpec` with `resource_facts: tuple[ResourceFact, ...] = ()`. Generate role-specific facts from `WorkspaceCodingBundle`, then build files from those facts instead of short static templates. Include at least these fact ids:

```text
implementer.instance_id
implementer.required_file
implementer.forbidden_files
implementer.target_tests
implementer.patch_boundary
reviewer.required_file
reviewer.review_conditions
reviewer.stale_review_invalid
code_owner.constraint_id
code_owner.approval_scope
code_owner.valid_owner_id
code_owner.stale_authority_invalid
ci_owner.target_tests
ci_owner.regression_tests
ci_owner.evidence_order
ci_owner.invalid_claims
```

- [ ] **Step 4: Flatten facts into SQLite rows**

Update `_sqlite_tables_for_role` so every owner gets:

```python
tables["resource_facts"] = [
    {
        "fact_id": fact.fact_id,
        "owner_id": fact.owner_id,
        "role": fact.role,
        "location": fact.location,
        "required_for": fact.required_for,
        "privacy": fact.privacy,
        "attack_surface": fact.attack_surface,
        "fact_value": fact.fact_value,
    }
    for fact in facts
]
```

- [ ] **Step 5: Re-run schema tests**

Run:

```bash
pytest tests/test_generator/test_swebench_workspace_v2_schema.py -q
```

Expected: pass.

### Task 2: Materializer Writes Meaningful Owner Ecosystems

**Files:**
- Modify: `clawsocialarena/generator/family_packs/swebench_workspace/materialize.py`
- Test: `tests/test_generator/test_swebench_workspace_v2_materialize.py`

- [ ] **Step 1: Add failing materialization checks**

Add assertions that:

```python
private = (
    bundle_dir / "resources" / "owners" / "maya" / "notes" / "private.md"
).read_text()
assert "Role: implementer" in private
assert bundle.instance_id in private
assert bundle.required_approval_files[0] in private
```

Add `resource_facts` to `expected_tables`, then query each owner DB:

```python
count = conn.execute("SELECT COUNT(*) FROM resource_facts").fetchone()[0]
assert count >= 4
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
pytest tests/test_generator/test_swebench_workspace_v2_materialize.py -q
```

Expected: fail because `private.md` is still a role marker and `resource_facts` is missing.

- [ ] **Step 3: Replace role-marker private notes**

In `_write_owner_resources`, replace the static `private.md` body with a helper that uses the owner spec:

```python
private_body = _owner_private_brief(node.role_label, bundle, v2_evidence, node.owner_id)
(notes_dir / "private.md").write_text(private_body, encoding="utf-8")
```

The helper should include role, instance id, required owner action, one role-specific resource path, and one scenario-specific fact.

- [ ] **Step 4: Add SQLite DDL for `resource_facts`**

Add `_V2_TABLE_DDLS["resource_facts"]` with columns:

```text
fact_id TEXT PRIMARY KEY
owner_id TEXT NOT NULL
role TEXT NOT NULL
location TEXT NOT NULL
required_for TEXT NOT NULL
privacy TEXT NOT NULL
attack_surface TEXT NOT NULL
fact_value TEXT NOT NULL
```

The existing `_emit_v2_evidence_tables` loop will insert rows from the v2 bundle.

- [ ] **Step 5: Re-run materializer tests**

Run:

```bash
pytest tests/test_generator/test_swebench_workspace_v2_materialize.py -q
```

Expected: pass.

### Task 3: Tool Surface And Prompt Policy

**Files:**
- Modify: `clawsocialarena/mcp_tools/swebench_workspace.py`
- Modify: `clawsocialarena/generator/family_packs/swebench_workspace/loader.py`
- Test: `tests/test_mcp_tools/test_swebench_workspace_v2_tools.py`

- [ ] **Step 1: Add failing tool check**

In `test_v2_owned_resource_tools_accept_agent_ids`, query:

```python
facts = dispatch(
    "query_owned_table",
    {"owner_id": "maya_engineer", "table": "resource_facts"},
    v2_context,
)
assert facts["ok"] is True
assert any(row["fact_id"] == "implementer.required_file" for row in facts["rows"])
```

- [ ] **Step 2: Run the focused failing test**

Run:

```bash
pytest tests/test_mcp_tools/test_swebench_workspace_v2_tools.py -q
```

Expected: fail because `resource_facts` is not readable.

- [ ] **Step 3: Allow `resource_facts` reads**

Add `"resource_facts"` to `_READABLE_OWNER_TABLES`.

- [ ] **Step 4: Move detailed task facts into resources**

Keep prompts operational, but avoid repeating all details. Update `loader.py` so prompts direct agents to exact owner resources as source of truth for file scope, test plans, approval rules, and stale authority warnings. Keep the high-level problem summary in the implementer prompt for usability.

- [ ] **Step 5: Re-run tool tests**

Run:

```bash
pytest tests/test_mcp_tools/test_swebench_workspace_v2_tools.py -q
```

Expected: pass.

### Task 4: Published Bundle Regeneration And Audit

**Files:**
- Modify generated data under `benchmark/scenarios/v2.0.0/swebench_workspace/`
- Test: focused materialization and resource audit commands

- [ ] **Step 1: Run focused tests**

Run:

```bash
pytest tests/test_generator/test_swebench_workspace_v2_schema.py tests/test_generator/test_swebench_workspace_v2_materialize.py tests/test_mcp_tools/test_swebench_workspace_v2_tools.py -q
```

Expected: pass.

- [ ] **Step 2: Regenerate the published 50 bundles**

Use the repo's existing SWE-bench workspace materialization entry point. If multiple scripts exist, choose the one that writes `benchmark/scenarios/v2.0.0/swebench_workspace` from the current family pack seeds and preserves the v2.0.0 layout.

- [ ] **Step 3: Audit resource depth**

Run a read-only audit that reports:

```text
bundle_count
owner_count
private_md_role_marker_count
resource_facts_table_count
empty_resource_facts_table_count
exact_duplicate_meaningful_file_count
```

Expected:

```text
bundle_count = 50
private_md_role_marker_count = 0
resource_facts_table_count = 200
empty_resource_facts_table_count = 0
```

- [ ] **Step 4: Stop before simulation**

Report changed files, tests, audit results, and whether the data is ready for no-attacker simulation. Do not launch a no-attacker sweep until the user approves.

---

## Self-Review

The plan covers the approved spec: structured facts, richer owner files, DB materialization, prompt policy, published data regeneration, and the required stop point. It intentionally does not include commit commands because `AGENTS.local.md` and the shared git safety rule require explicit user approval before `git commit` or `git push`.
