# Travel scenario descriptions

Per-task design notes for the Phase 5 travel family pack. The travel
family occupies two cells in the Phase 5 grid:

- `CU-D-travel` — three CU triad tasks (traveler + partner_hotel + corp_travel approver).
- `MG-C-travel` — three MG group tasks (organizer + 3 co_travelers + partner_hotel).

All six base tasks are seeded from English-translated TravelBench
(ACL 2026) rows; the seed module preserves a sha256 of each original
Chinese query so source fidelity is auditable. Topology shapes reuse
Framing A (existing triad / group patterns); the novelty axes are the
domain resources, the bargaining-bound MCP tool surface, the
travel-flavored persona / loyalty / partner state, and the four
canonical attack recipes' travel-idiom payloads.

## Cells

- `cu_d/` — three CU-D-travel tasks, each a solo traveler driving a
  single partner_hotel negotiation with a corp_travel delegated
  approver gate. Identity variation across tasks rotates traveler
  loyalty tier, destination, and rate band.
- `mg_c/` — three MG-C-travel tasks, each an organizer collecting
  consent from three co_travelers on group_dm before negotiating
  with one partner_hotel and writing the final group booking.

## Status

| Stage | State |
|---|---|
| Loader + materializer | landed (commit `ab626bc`) |
| Scenario docs | this directory |
| Materialization (Task 8) | pending |
| No-attacker smoke | pending |
| Stress smoke | pending |

Per-task pages document the planned scenario as it exists in the
loader / materializer code; the "Simulation Log" section in each
page is empty until Task 8 lands the materialized bundles and the
no-attacker smoke runs.

## Source

- Seed module: `clawsocialarena/generator/family_packs/travel/seed_data/travel_seeds.py`
- Lift table: `clawsocialarena/generator/family_packs/travel/seed_data/travelbench_lifts.json`
- Loader: `clawsocialarena/generator/family_packs/travel/loader.py`
- Materializer: `clawsocialarena/generator/family_packs/travel/materialize.py`
- MCP tools: `clawsocialarena/mcp_tools/travel.py` (16 in-process handlers)
- Plan: `docs/superpowers/plans/travel/2026-05-16-travel-family-first-ship.md`
