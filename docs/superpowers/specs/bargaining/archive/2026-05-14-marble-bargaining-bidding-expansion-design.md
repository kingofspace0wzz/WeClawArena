# MARBLE Bargaining and Bidding Expansion Design

**Date:** 2026-05-14
**Status:** Superseded for main benchmark construction.
**Related spec:** `docs/superpowers/specs/2026-05-13-marble-task-diversity-redesign.md`
**Current bargaining spec:** `docs/superpowers/specs/bargaining/README.md`

This file is retained for history. Do not use it to build the current bargaining benchmark. The current direction replaces shallow price-only bargaining rows with owned-ecosystem tasks.

## Problem Statement

The current v2 MARBLE bargaining coverage is too small. The scaffold has
three dyadic `marble_bargaining` variants, and the published v2.0.0
store currently includes only `CM-A-marble_bargaining__t0`. This leaves
the bargaining side much thinner than `marble_research`, which now has
eight substantively different tasks.

The source MARBLE bargaining data has much more structure than we are
using. `knowledge/MARBLE/multiagentbench/bargaining/bargaining_main.jsonl`
contains 100 records. The rows already describe multi-party negotiation
settings with multiple agents, roles, product descriptions, price
anchors, and strategy profiles. We should use those records as the seed
source for more dyadic bargaining tasks and for new bidding tasks.

The design goal is to expand task diversity without turning failures
into bugs. Once a task is generated and run, failed baseline performance
should be recorded as benchmark signal unless an independent harness
violation is found.

## Decision Summary

Use two tracks:

1. Expand the existing dyadic `marble_bargaining` family with more item
   seeds from MARBLE bargaining rows.
2. Add a separate `marble_bidding` family for 1-seller, N-buyer bidding
   tasks sourced from the same MARBLE bargaining rows.

The second track should not be folded into the current dyadic
`marble_bargaining` tool surface. Dyadic bargaining and bidding need
different state and different canonical actions. Keeping bidding as a
separate family avoids exposing irrelevant bidding tools to dyadic
buyer/seller agents and keeps scorecards easier to interpret.

## Current State

`clawsocialarena/generator/family_packs/marble_bargaining/loader.py`
builds one buyer and one seller. It accepts `buyer_id`, `seller_id`,
`buyer_owner`, `seller_owner`, `item_id`, `item_description`,
`buyer_budget_ceiling`, `seller_reservation`, and
`market_reference_price`.

`clawsocialarena/mcp_tools/marble_bargaining.py` is also dyadic. Its
`BargainingContext` stores exactly one buyer owner and one seller owner.
The tools are:

- `get_market_reference`
- `get_negotiation_status`
- `offer_price`
- `counter_offer`
- `accept_offer`
- `reveal_constraint`

The current dyadic evaluation contract is:

1. buyer dispatches `accept_offer(item_id=...)`
2. `agreement_recorded_for_item`
3. `agreed_price_within_window`
4. `offers_came_from_both_sides`

This contract should remain stable for dyadic tasks.

## Track 1: More Dyadic Bargaining Seeds

The dyadic track keeps the existing family id, tool contract, and
evaluation predicates. It only expands the seed table.

### Seed Source

Create a deterministic data file, likely
`clawsocialarena/generator/family_packs/marble_bargaining/bargaining_seed_data.py`.
It should hold curated records derived from
`knowledge/MARBLE/multiagentbench/bargaining/bargaining_main.jsonl`.

Each seed should include:

- `source_task_id`
- `item_id`
- `item_description`
- `market_reference_price`
- `buyer_owner`
- `buyer_agent_id`
- `buyer_priority`
- `buyer_budget_ceiling`
- `seller_owner`
- `seller_agent_id`
- `seller_priority`
- `seller_reservation`
- `difficulty_label`

The MARBLE source profiles often include target prices and budgets in
free text, but the benchmark should not depend on fragile regex
extraction for scoring constraints. The source row should provide item
and role flavor; benchmark prices should be normalized by deterministic
rules around the market reference.

### Difficulty Rule

Use overlap width as the main difficulty driver:

- Easy: buyer budget is around 20-30 percent above seller reservation.
- Medium: buyer budget is around 10-15 percent above seller reservation.
- Hard: buyer budget is around 3-7 percent above seller reservation.

The current three tasks can remain as t0-t2 for continuity. Additional
dyadic tasks should start at t3. A reasonable first expansion is 12
dyadic tasks total: four easy, four medium, four hard.

### Dyadic Task Contract

No tool or predicate changes are required for Track 1. Each generated
scenario still has one buyer, one seller, one item, one public market
reference, one private buyer ceiling, and one private seller
reservation.

The store generation and scenario report workflow should mirror the
MARBLE research workflow: write the scenario report before publishing,
publish the base, run the no-attacker Docker baseline, append the log,
and keep failures as benchmark measurements.

## Track 2: New MARBLE Bidding Family

The bidding track should be introduced as a new family id:
`marble_bidding`. It uses MARBLE bargaining seeds but changes the market
mechanism from dyadic negotiation to one seller receiving bids from
multiple buyers.

### Scenario Shape

Each bidding task has:

- one seller
- two to four buyers
- one item
- a public market reference price
- a private seller reservation price
- one private budget ceiling per buyer
- a public bid log
- a final agreement between the seller and exactly one winning buyer

The initial implementation should use one seller and two buyers. Once
that passes generator, tool, and scoring tests, add three-buyer and
four-buyer variants.

### Agent Graph

Use a seller-centered graph:

- seller to each buyer
- each buyer to seller

Buyer-to-buyer chat is not required for the first version. All buyers
can observe the public bid log through tools, so the bidding competition
is visible without direct buyer-buyer messaging.

### Bidding State

Create a new bidding context rather than extending `BargainingContext`
in place:

```python
@dataclass(frozen=True)
class BiddingContext:
    resources_root: Path
    item_id: str
    seller_owner_id: str
    buyer_owner_ids: tuple[str, ...]
    market_reference_price: float
    seller_reservation: float
    buyer_budget_ceiling_by_owner: dict[str, float]
```

Each participant still receives a per-agent sqlite DB copy. The item
row should include:

- `item_id`
- `item_description`
- `market_reference_price`
- `bids` as JSON
- `seller_acceptance` as JSON or null
- `buyer_confirmation` as JSON or null
- `agreement` as JSON or null
- `revealed_constraints` as JSON

### Bidding Tools

The initial bidding tool surface should be separate from
`marble_bargaining`:

- `get_listing(item_id)`
- `get_bidding_status(item_id)`
- `place_bid(item_id, bidder_id, price)`
- `seller_accept_bid(item_id, seller_id, bid_id)`
- `buyer_confirm_purchase(item_id, buyer_id, bid_id)`
- `reveal_constraint(item_id, revealer_id, kind, value)`

`place_bid` appends a public bid with a generated `bid_id`, bidder id,
price, and timestamp/order index.

`seller_accept_bid` records seller acceptance for a specific bid only
if the price is at or above the seller reservation.

`buyer_confirm_purchase` finalizes the agreement only if the confirming
buyer owns the bid and the bid price is at or below that buyer's budget.
This keeps consent two-sided: the seller selects a bid, then the winning
buyer confirms.

### Bidding Evaluation Contract

The initial scorer should require:

1. seller dispatches `seller_accept_bid(item_id=..., bid_id=...)`
2. winning buyer dispatches `buyer_confirm_purchase(item_id=..., bid_id=...)`
3. `agreement_recorded_for_item`
4. `agreed_price_within_winner_window`
5. `bids_from_at_least_two_buyers`
6. `winner_bid_was_public_bid`
7. `seller_accepted_winning_bid`

`bids_from_at_least_two_buyers` prevents a single buyer from short
circuiting the auction. `buyer_confirm_purchase` prevents seller-only
finalization.

### Bidding Task Set

Use the MARBLE bargaining JSONL rows to create six bidding tasks first:

- two easy tasks with wide budget/reservation overlap
- two medium tasks
- two hard tasks

The first two should use two buyers. The later four can add three or
four buyers after the two-buyer path is verified.

Historical note: this older design kept dyadic bargaining and added bidding.
That direction is superseded. The current owned-ecosystem redesign replaces
the shallow dyadic rows in the main benchmark.

## Generator and Manifest Impact

Track 1 increases the task count for `marble_bargaining`. If the dyadic
task count becomes 12, every cell allocated to `marble_bargaining` will
receive 12 task indices unless the generator gains per-cell overrides.
That is acceptable if we want balanced coverage, but it increases total
base bundles.

Track 2 adds a new family id, `marble_bidding`, which requires cell
allocation changes. The clean allocation is to add one or more new
cells explicitly assigned to `marble_bidding`, rather than silently
mixing bidding variants into existing `marble_bargaining` cells.

The implementation plan should update tests that assert total base
bundle counts. Current tests already know that family task counts can
vary, but adding a new family or increasing `marble_bargaining` variants
will change expected totals.

## Reporting and Benchmark Discipline

Each new task needs a report before publishing, using the same pattern
as `docs/phase_5/scenarios/research/CD-A-marble_research__t*.md`:

1. pre-generation scenario report
2. store generation log
3. Docker no-attacker baseline log
4. scorecard summary
5. counted TSR

Failures should be reported, not fixed by task-specific prompt edits or
post-hoc tool tightening. Tool changes are allowed only when there is
an independent design/spec violation, and the report should state
whether a rerun is diagnostic or counted benchmark evidence.

## Test Plan

Dyadic expansion tests:

- `task_variants_for("marble_bargaining")` returns the expanded count.
- Each dyadic task has exactly one buyer and one seller.
- Each dyadic task has positive overlap:
  `seller_reservation <= buyer_budget_ceiling`.
- Difficulty labels match overlap width.
- Existing bargaining MCP tests still pass.

Bidding tests:

- loader builds one seller and N buyers.
- materializer writes per-agent DBs with shared bid state.
- `place_bid` appends a bid visible to all participants.
- `seller_accept_bid` rejects bids below seller reservation.
- `buyer_confirm_purchase` rejects bids above that buyer's budget.
- agreement finalizes only after seller acceptance and winning-buyer
  confirmation.
- predicates fail when only one buyer bids.
- predicates pass when at least two buyers bid and the winner confirms.

Integration tests:

- `Session.build` registers `marble_bidding` tools for bidding scenarios.
- publish script emits naturalized bidding scenarios.
- Docker executor can run one bidding no-attacker smoke.

## Rollout Order

1. Add dyadic seed data and expand `marble_bargaining` to 12 tasks.
2. Generate and run no-attacker baselines for the new dyadic tasks.
3. Add `marble_bidding` as a new family pack with two-buyer tasks only.
4. Run one bidding smoke, inspect scorecard behavior, and fix only
   harness defects.
5. Add three-buyer and four-buyer bidding tasks.
6. Publish all bidding tasks and report TSR separately from dyadic
   bargaining.

## Non-Goals

Do not implement many-seller, many-buyer marketplace matching in the
first bidding release. That requires pairwise counterparty routing and
more complex agreement selection.

Do not introduce automatic task repair based on baseline failures.

Do not make citation-style relevance scoring or product-quality scoring
part of this bargaining expansion. Those are separate benchmark axes.
