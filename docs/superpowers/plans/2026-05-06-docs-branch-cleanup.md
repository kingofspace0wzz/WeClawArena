# Documentation and Branch Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current benchmark and branch state easy to find, while preserving old plans as historical records.

**Architecture:** Keep one current-status page and one documentation index as the reader entry points. Archive superseded root and April 17 implementation plans, then leave pointer stubs at the old paths so links do not fail.

**Tech Stack:** Markdown documentation, git worktrees, repository-local benchmark artifacts.

---

### Task 1: Create Current Entry Points

**Files:**
- Create: `docs/project_status.md`
- Create: `docs/DOCUMENTATION_INDEX.md`

- [x] **Step 1: Document current project state**

Write a short status page that records the canonical branch, active docs, benchmark target, retained batches, and branch/worktree status.

- [x] **Step 2: Document the doc map**

Write an index that separates current docs, architecture references, execution plans, team-facing docs, and archived records.

### Task 2: Archive Superseded Plans

**Files:**
- Move: `docs/design.md` to `docs/archive/superseded/design.md`
- Move: `docs/plan.md` to `docs/archive/superseded/plan.md`
- Move: `docs/superpowers/plans/2026-04-17-clawsocialarena-v2.md` to `docs/archive/superseded/superpowers/plans/2026-04-17-clawsocialarena-v2.md`
- Create pointer stubs at the original paths.

- [x] **Step 1: Preserve historical content**

Archive the full old files rather than deleting them.

- [x] **Step 2: Preserve stable links**

Create short pointer files at the old paths that send readers to `docs/project_status.md` and the archived copy.

### Task 3: Update Landing Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/benchmark_dataset_guide.md`
- Modify: `docs/preregistration.md`
- Modify: `docs/superpowers/specs/2026-04-17-clawsocialarena-v2-design.md`

- [x] **Step 1: Point README to current state**

Replace old April 17 plan links and obsolete 550-row Phase E instructions with the current 680-row scaffold and retained-batch status.

- [x] **Step 2: Correct benchmark guide status**

Record that the retained `0061`, `0064`, and `0065` batches are diagnostic only after evaluator and construction fixes.

- [x] **Step 3: Add status banners to older references**

Mark older spec and preregistration documents as architecture/reference material whose batch counts must be checked against `docs/project_status.md`.

### Task 4: Verify Links and Branch Inventory

**Files:**
- No source changes expected.

- [x] **Step 1: Search for stale primary links**

Run:

```bash
rg "docs/design\.md|docs/plan\.md|2026-04-17-clawsocialarena-v2\.md|550-variant benchmark|batch-002" README.md docs -n
```

Expected: remaining hits are either archived content, pointer stubs, or explicit historical notes.

- [x] **Step 2: Confirm worktree state**

Run:

```bash
git worktree list --porcelain
git status --short --branch
```

Expected: current checkout remains on `main`; `phase-I-governance` and `v2-refactor` remain untouched worktrees.
