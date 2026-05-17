# Travel Implementation Plans

Current implementation planning should follow the active travel design specs once they are written. The first implementation plan is `2026-05-16-travel-family-first-ship.md` (rev 2), which adds a new `travel` family pack to the Phase 5 grid with two cells (`CU-D-travel`, `MG-C-travel`) and lays the ground for later topology-distinctive expansions.

Travel is seeded from `knowledge/TravelBench` (ACL 2026), reusing the user-intent stems and `user_profile` blocks while reimplementing the ten travel tools as our own MCP servers with deterministic synthetic backing stores. The TravelBench sandbox cache, embedding service, and judge model are not used.

## Framing

The first ship uses **framing A**: travel is a new domain that reuses existing topology shapes. The novelty layer lives in resources (loyalty tier, passport, dynamic pricing, vendor inventory), attacks (booking-confirmation prompt injection, loyalty/passport exfiltration, stale-mandate booking approval bypass, constraint-inflation hijacking), MCP tool surface (ten travel tools backed by deterministic stores), and personas. The coordination structures themselves are inherited:

- `CU-D-travel` mirrors the bargaining triad: traveler + partner_hotel + approver.
- `MG-C-travel` mirrors tau2_telecom-style group: organizer + 3 co-travelers + partner_hotel.

Framing B (genuinely travel-distinctive topology shapes such as sequential commit chains with rollback, vendor-coalition cross-terms, or asymmetric joint decision scopes) is interesting future work; it is deferred to a follow-up plan and listed in the long-term coverage table below.

## Cell Allocation

The current `CELL_ALLOCATION` in `clawsocialarena/generator/cell_allocation.py` is 16 cells (categories `CD, MC, CU, MG, HS, CM, AM` with slots A, B, and a C for `CU` and `CM` taken by `marble_bidding`). The first travel ship adds two new third-slot cells:

| Cell | Topology shape inherited from | Status |
|---|---|---|
| `CU-D-travel` | `CU-A-marble_bargaining` triad (2-agent + delegated approver) | First-ship (rev 2) |
| `MG-C-travel` | `MG-A-tau2_telecom` group (primary holder + members) | First-ship (rev 2) |
| `AM-C-travel` | Tier-asymmetric party (VIP + companion + regular) | Deferred follow-up |
| `CM-D-travel` | Rival travelers compete for scarce inventory | Deferred follow-up |

| Topology-distinctive deferred work | Property exploited |
|---|---|
| Sequential commit chain with rollback (D1) | Temporal booking dependencies; cancellation cascade |
| Vendor-coalition cross-terms (D3) | Vendor terms condition each other through a private partner network |
| Asymmetric joint decision scopes (D4) | Heterogeneous consensus rules within one group |

## Plan History

| Plan | Status |
|---|---|
| `2026-05-16-travel-family-first-ship.md` (rev 2) | Current first-ship plan: spec + cell_allocation updates, two cells, ten MCP servers, four attack recipes, 30-variant smoke gate. |
| rev 1 (same file, prior version) | Reviewed by codex 2026-05-16, verdict REVISE. Four hard blockers (registry API mismatch, cell-allocation collision, attack recipe dispatch path, evaluation_criteria schema). Rev 2 addresses all four. Codex report at `benchmark/reviews/2026-05-16-travel-first-ship-plan-review.md`. |
