# Batch A Report -- Registry + Cell Allocation

## Header

| Field | Value |
|---|---|
| batch_id | A |
| start_ts | 2026-05-10 18:55 PT |
| end_ts | 2026-05-10 19:05 PT |
| wall_clock_minutes | ~10 |
| commit_sha_before | 1acce51 |
| commit_sha_after | unchanged (no commits this batch) |
| author_agent | claude-opus-4-7 |
| reviewer_agent | codex (humanize:ask-codex) |
| naturalization_model | gpt-5.2 (not exercised in this batch) |
| agent_model | gpt-4.1-mini (not exercised in this batch) |

## Test metrics

| Metric | Value |
|---|---:|
| total_tests_run | 593 |
| new_tests_added | 32 |
| passing | 593 |
| failing | 0 |
| skipped | 0 |
| pre_existing_failures (out-of-scope suites) | 7 (unchanged) |
| new_regressions | 0 |

Suites covered in regression sweep: `tests/test_gateway`, `tests/test_mcp_tools`, `tests/test_generator`, `tests/test_eval`. Out-of-scope suites (`tests/test_saf`, `tests/test_scenario`, `tests/test_analysis`, etc.) intentionally not re-run; the 7 pre-existing failures live there and are unrelated to Batch A.

### New tests

`tests/test_generator/test_family_pack_registry.py` (12 tests):

- Registry covers all 6 expected family_ids
- Every entry carries required fields (load_fn, materialize_fn, session_context_keys)
- get_entry returns the right entry; raises KeyError listing known ids on a typo
- 6 parametrized `load_and_materialize` tests (one per family) — each produces a bundle dir with scenario.json, scenario.gt.json, family_pack_context.json, docker-compose.yml, and a bundle whose scenario.family_id matches
- load_kwargs forwarding works (verified on tau2_retail with custom household_id)
- session_context_keys validation

`tests/test_generator/test_cell_allocation.py` (20 tests):

- Exactly 14 cells; cell_indexes are 0..13 in order
- Every category appears exactly twice
- Each cell has slot in {"A", "B"}
- Each category uses both slots
- Per-family cell counts match the spec section 2 table:
  - marble_research 3, marble_bargaining 2, wildclaw_social 2, tau2_retail 2, tau2_telecom 3, tau2_airline 2 (sum = 14)
- cells_for_family parametrized over all 6 families
- cell_for / cell_by_index roundtrip and error paths
- cell_id format frozen for downstream report tooling
- Pilot math sentinel: `14 * 3 * 3 == 126` (cells x base tasks x difficulty tiers)
- CellSpec is frozen (cannot be mutated)

## Functional metrics

| Metric | Value |
|---|---:|
| families registered | 6 |
| families expected (spec section 1) | 6 |
| cells in allocation | 14 |
| cells expected (spec section 2) | 14 |
| per-family cell count match | ✓ exact match against spec |
| categories with both slots present | 7 (all of CD/MC/CU/MG/HS/CM/AM) |
| `load_and_materialize` round-trip success per family | 6/6 |

### Per-family registration

| family_id | session_context_keys |
|---|---|
| tau2_retail | household_id, primary_owner_id, secondary_owner_ids |
| tau2_airline | group_id, organizer_owner_id, traveler_owner_ids |
| tau2_telecom | account_id, primary_owner_id, secondary_owner_ids |
| marble_research | proposal_id, convener_owner_id, peer_owner_ids |
| marble_bargaining | item_id, buyer_owner_id, seller_owner_id, buyer_budget_ceiling, seller_reservation, market_reference_price |
| wildclaw_social | meeting_id, organizer_owner_id, participant_owner_ids |

### Cell allocation table (frozen)

| cell_index | category | slot | family_id |
|---:|---|---|---|
| 0 | CD | A | marble_research |
| 1 | CD | B | tau2_airline |
| 2 | MC | A | wildclaw_social |
| 3 | MC | B | tau2_airline |
| 4 | CU | A | marble_bargaining |
| 5 | CU | B | tau2_retail |
| 6 | MG | A | tau2_telecom |
| 7 | MG | B | marble_research |
| 8 | HS | A | marble_research |
| 9 | HS | B | tau2_telecom |
| 10 | CM | A | marble_bargaining |
| 11 | CM | B | wildclaw_social |
| 12 | AM | A | tau2_retail |
| 13 | AM | B | tau2_telecom |

## Files

### Added

| Path | Lines |
|---|---:|
| clawsocialarena/generator/family_pack_registry.py | 146 |
| clawsocialarena/generator/cell_allocation.py | 108 |
| tests/test_generator/test_family_pack_registry.py | 86 |
| tests/test_generator/test_cell_allocation.py | 130 |
| docs/phase_5/BATCH_A_REPORT.md | (this file) |
| **Total** | **470 + report** |

### Modified

None.

### Removed

None.

## Cost

| Field | Value |
|---|---:|
| tokens_in | 0 |
| tokens_out | 0 |
| cost_usd | 0.00 |
| model_used | n/a (no LLM calls this batch) |

## Outstanding work for downstream batches

- Batch B will consume `FAMILY_LOADERS` to author one naturalization template per family. The registry's `load_fn` is the canonical entry point each template's render-test will call.
- Batch C will iterate over `all_cells()` × 3 tiers × 3 tasks = 126 to drive the base-task generator.
- Batch D will key per-pack attack payloads off `family_id`.
- Batch E + F consume the same registry + allocation as the orchestration source of truth.

## Known soft spots flagged for later

- `FamilyPackEntry.session_context_keys` is advisory only -- it is not currently enforced when `Session.register_family_pack_tools` is called. A future safety pass could cross-check the keys before dispatch and warn on missing required keys. Not blocking for Phase 5 because each Session.build dispatch branch falls back to sensible per-pack defaults when context is empty.
- The `marble_bargaining` registry entry has 6 context keys (more than any other pack) because the buyer/seller constraints (budget_ceiling, reservation_price, market_reference_price) are numeric and have no sensible default outside the seed. Phase-5 cell generation must populate these explicitly per task.

## Codex review

To be appended below after `humanize:ask-codex` runs.

---

### Codex verdict

**BATCH_A_REVIEW_VERDICT: APPROVED**

Codex independently reran both new test files through the repo venv (`12 passed` for the registry, `20 passed` for the cell allocation) and confirmed:

- Registry covers all 6 required `family_id`s; `session_context_keys` tuples match the keys actually consumed in `clawsocialarena/gateway/session.py:228`.
- 14-cell allocation table matches `docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md` section 2 exactly.

**Non-blocker observations** (from codex; none block downstream batches):

1. `cells_for_family()` silently returns `()` for an unknown `family_id` instead of raising like `get_entry()` does. A later Batch C or E typo could under-generate work without an obvious stop.
2. No automated cross-module invariant test ties `CELL_ALLOCATION` family ids to `FAMILY_LOADERS` keys, or ties each registry `session_context_keys` tuple to the six branches in `Session.register_family_pack_tools()`. Current code is consistent; this is a drift risk, not a present defect.
3. The docstring on `Session.register_family_pack_tools()` is stale -- still says only `tau2_retail` is supported, while the implementation handles all six families.

**Codex's recommended next step:** "proceed to Batch B, but add one cross-module invariant test up front so later batches fail fast if allocation ids, registry ids, or session context keys drift apart."

Codex output transcript: `.humanize/skill/2026-05-10_20-42-23-76524-bca8772d/output.md`
