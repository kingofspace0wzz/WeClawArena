# Travel scenario descriptions

Per-task design notes for the Phase 5 travel family pack. The travel
family occupies two cells in the Phase 5 grid:

- `CU-D-travel` — 10 CU triad tasks (traveler + partner_hotel + corp_travel approver).
- `MG-C-travel` — 10 MG group tasks (organizer + 3 co_travelers + partner_hotel).

All 20 base tasks are seeded from English-translated TravelBench
(ACL 2026) rows; the seed module preserves a sha256 of each original
Chinese query so source fidelity is auditable. Topology shapes reuse
Framing A (existing triad / group patterns); the novelty axes are the
domain resources, the bargaining-bound MCP tool surface, the
travel-flavored persona / loyalty / partner state, and the four
canonical attack recipes' travel-idiom payloads.

## Cells

- `cu_d/` — 10 CU-D-travel tasks, each a solo traveler driving a
  single partner_hotel negotiation with a corp_travel delegated
  approver gate. Identity variation across tasks rotates traveler
  loyalty tier, destination, and rate band. Lift rotation covers the
  three available CU lifts (`tb_mt_1`, `tb_st_6`, `tb_st_7`).
- `mg_c/` — 10 MG-C-travel tasks, each an organizer collecting
  consent from three co_travelers on group_dm before negotiating
  with one partner_hotel and writing the final group booking. Each
  co-traveler is seeded from a distinct lift so consent collection
  is realistically heterogeneous. Consensus threshold is `3` for
  every MG seed (matching the 3 co-traveler group).

## Status

| Stage | State |
|---|---|
| Loader + materializer | landed (commit `ab626bc`) |
| Initial 6-task scenario docs | landed |
| Task expansion to 20 base tasks | landed (this directory now covers t0..t9 per cell) |
| Persona guardrail append | landed 2026-05-18 (protected-field non-disclosure, consent integrity, approval-gate trust) |
| Materialization | landed in `benchmark/scenarios/v2.0.0/travel` |
| No-attacker smoke | landed (50 / 100 baseline TSR per cell on the 2026-05-18 redesign-v2 sweep) |
| Stress smoke | landed (`benchmark/phase5/pilot/travel_attack_sweep_20260517/`) |
| Redesign-v1 smoke (10 variants) | landed (`benchmark/phase5/pilot/travel_redesign_smoke_20260518/`) |
| Redesign-v2 full sweep (100 variants) | landed (`benchmark/phase5/pilot/travel_redesign_v2_20260518/`) |

Per-task pages document the planned scenario as it exists in the
loader / materializer code. Each page closes with a Simulation Log
pointer to the most recent pilot run.

## Source

- Seed module: `clawsocialarena/generator/family_packs/travel/seed_data/travel_seeds.py`
- Lift table: `clawsocialarena/generator/family_packs/travel/seed_data/travelbench_lifts.json`
- Loader: `clawsocialarena/generator/family_packs/travel/loader.py`
- Materializer: `clawsocialarena/generator/family_packs/travel/materialize.py`
- MCP tools: `clawsocialarena/mcp_tools/travel.py` (16 in-process handlers)
- Attack recipes: `clawsocialarena/attacks/stress_recipes/travel_mode_local_playbooks.py`
- LLM ASR judge: `clawsocialarena/eval/travel_asr_judge.py`
- Predicates: `clawsocialarena/eval/predicates/travel/__init__.py`
- Specs: `docs/superpowers/specs/travel/` (data construction, attack vectors, task success, LLM ASR)
- Plan: `docs/superpowers/plans/travel/2026-05-16-travel-family-first-ship.md`
