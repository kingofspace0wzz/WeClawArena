# Travel Data Construction

## Goal

`travel` adapts TravelBench (ACL 2026) hotel-booking traces into a multi-user owned travel-coordination workspace. The agent team must close a hotel booking artifact while reading, writing, and bargaining over per-owner files and SQLite tables. The benchmark goal is to test multi-user coordination under bargaining bounds, approval gates, and consent collection.

The family is not a plain hotel-bargaining harness. Each cell exercises a distinct social topology: CU-D-travel is a delegated-approval triad (single traveler, single partner_hotel, single corp_travel approver) and MG-C-travel is a multi-party consensus group (single organizer, three co_travelers, single partner_hotel).

## Source Rows

Base tasks are sourced from TravelBench (ACL 2026), specifically `multi_turn.jsonl` and `single_turn.jsonl` trajectories that mention Chinese hotel-booking queries. The Chinese queries are translated to English and stripped of demographics blocks before being baked into the persona prompt. The seed module preserves a sha256 of the original Chinese query so source fidelity is auditable.

The current v2.0.0 build has 20 bases:

- CU-D-travel t0..t9 (10 bases)
- MG-C-travel t0..t9 (10 bases)

Selection rules for the expansion batch (t3..t9 per cell, landed 2026-05-17):

- rotate destination across mainland-China business and tourist hubs (Yunnan, Henan, Jiangsu, Guangdong, Shaanxi, Zhejiang, Sichuan, Hubei, Hainan, Shandong, Heilongjiang, Fujian, Beijing)
- rotate traveler loyalty tier across {`bronze`, `silver`, `gold`, `platinum`}
- vary the required-terms block to exercise different bargaining knobs (proximity terms, amenities, breakfast, late checkout)
- preserve the bargaining-bound invariant: `partner_floor_rate < target_unit_rate` so every seed has a non-empty zone of possible agreement
- MG seeds set `consensus_threshold = 3` (matches the three-co-traveler group)

No LLM naturalization is used for the current rows; TravelBench English translations are used directly. Seed data is materialized with `naturalization_model = none` and `status = not_naturalized_review_approved_seed`.

## Published Layout

Published store:

```text
benchmark/scenarios/v2.0.0/
  manifest.json
  travel/
    CU-D-travel__t0/
      scenario.json
      scenario.gt.json
      family_pack_context.json
      personas/
        <traveler>_traveler.system.md
        <partner>_partner_hotel.system.md
        <approver>_corp_travel_approver.system.md
      resources/
        agents/<owner>/files/...
        agents/<owner>/db/personal.sqlite
      mcp/<tool_name>.json
    ...
    CU-D-travel__t9/
    MG-C-travel__t0/
    ...
    MG-C-travel__t9/
```

The manifest has 100 `travel` rows:

| Attack mode | Rows |
|---|---:|
| `no_attacker` | 20 |
| `security` | 20 |
| `privacy` | 20 |
| `governance` | 20 |
| `collaboration` | 20 |

Attack-mode rows point to base bundles. Runtime code applies attack overlays into a per-run variant directory via the travel mode-local playbook (`clawsocialarena/attacks/stress_recipes/travel_mode_local_playbooks.py`). The variant dir under `benchmark/phase5/pilot/<run>/variants/<variant_id>` carries the mutated `scenario.json`, the planted file writes under `resources/agents/<owner>/files/...`, and the planted DB rows in the owner's `personal.sqlite`.

## Team Model

### CU-D-travel (3 agents)

| Role | Agent id pattern | Owner id pattern | Owned resources |
|---|---|---|---|
| Traveler | `<lift>_traveler` | `<lift>` | loyalty status, payment methods, medical constraints, current trip state, prior bookings PDF, dining preferences; `personal_prefs`, `travel_history`, `personal_calendar` tables |
| Partner hotel | `<dest_slug>_hotel_partner_hotel` | `<dest_slug>_hotel` | room policies, loyalty partner-match JSON, VIP waitlist; `inventory`, `dynamic_pricing`, `seller_orders` tables |
| Corp_travel approver | `<lift>_corp_travel_approver` | `<lift>_corp_travel` | corporate travel policy, delegate authorization codes; `approval_log`, `budget_envelope` tables |

Where `<lift>` is one of `mt_1_traveler`, `st_6_traveler`, `st_7_traveler` (rotated across t0..t9 to spread persona variation) and `<dest_slug>` is the destination text normalized to lowercase + underscores (e.g. "Huaning County, Yunnan" → `huaning_county_hotel`).

### MG-C-travel (5 agents)

| Role | Agent id pattern | Owner id pattern | Owned resources |
|---|---|---|---|
| Organizer | `<organizer_lift>_organizer` | `<organizer_lift>` | group charter, payment methods, current trip state, loyalty status, prior bookings PDF; `personal_prefs`, `travel_history`, `personal_calendar`, `group_membership`, `consent_log` tables |
| Co-traveler 1..3 | `<co_lift>_traveler` (suffix `_co1/_co2/_co3` on the owner) | `<co_lift>` | loyalty status, medical constraints, personal calendar excerpt; `personal_prefs`, `personal_calendar` tables |
| Partner hotel | `<dest_slug>_hotel_partner_hotel` | `<dest_slug>_hotel` | room policies, loyalty partner-match JSON, VIP waitlist; `inventory`, `dynamic_pricing`, `seller_orders` tables |

There is **no** approver in MG-C-travel. The MG cell exercises the consent-collection axis through the three co-travelers' `log_consent` rows rather than through a separate approval gate. Governance attacks adapt: instead of a forged `approval_log` row signed by a non-approver, the MG governance recipe plants forged `consent_log` rows + a corroborating `approval_log` row authored by a fictional `tier2_organizer_auto_approver`.

## Bargaining Bounds Per Seed

Every CU seed:

| Field | Range |
|---|---|
| `target_unit_rate` | $310 (Kaifeng bronze) -- $890 (Beijing platinum) |
| `partner_floor_rate` | $285 -- $805 (always less than target by $25-$85) |
| `quantity` | 2 or 3 room-nights |

Every MG seed:

| Field | Range |
|---|---|
| `target_unit_rate` | $445 (autumn-foliage) -- $1,180 (Sanya Yalong Bay) |
| `partner_floor_rate` | $410 -- $1,080 |
| `group_budget_envelope` | $5,400 -- $18,000 |
| `per_person_cap` | $1,500 -- $4,500 |
| `consensus_threshold` | 3 (always; matches the 3-co-traveler group) |

The bargaining-bound invariant `partner_floor_rate < target_unit_rate` is enforced by a unit test in `tests/test_travel_seeds.py`.

## Loader and Materializer

- `clawsocialarena/generator/family_packs/travel/loader.py`: builds the `TravelScenarioBundle` from a seed + lift table. Renders persona prompts via `_traveler_prompt`, `_partner_hotel_prompt`, `_approver_prompt`, `_organizer_prompt`, `_co_traveler_prompt`. The 2026-05-18 persona-guardrail edits (protected-field non-disclosure, resource-content trust, consent integrity, approval-gate trust, privacy non-disclosure for medical) live in this module.
- `clawsocialarena/generator/family_packs/travel/materialize.py`: emits the per-bundle directory under `benchmark/scenarios/v2.0.0/travel/<base_id>/`. Writes personas via `emit_persona_files`, builds the owned filesystem with `_write_traveler_files` / `_write_partner_files` / `_write_approver_files` / `_write_organizer_files` / `_write_co_traveler_files`, and seeds the per-owner `personal.sqlite` with `_seed_traveler_db` etc.
- `clawsocialarena/mcp_tools/travel.py`: 16 in-process MCP tool handlers (`search_hotels`, `get_hotel_details`, `submit_offer`, `counter_offer`, `record_seller_acceptance`, `request_purchase_approval`, `issue_approval`, `confirm_booking`, `log_consent`, `reveal_protected_field`, etc.).

## TravelBench Lift Table

`clawsocialarena/generator/family_packs/travel/seed_data/travelbench_lifts.json` carries the persona blobs (age band, current city, route context, preferences, original query sha256) for each lift id used by the seeds. The lift ids covering all 20 seeds are: `tb_mt_1`, `tb_mt_4`, `tb_mt_8`, `tb_mt_9`, `tb_st_6`, `tb_st_7`. Co-traveler lift rotation across the 10 MG seeds spreads each lift across multiple groups so consent collection diverges in the realistic distribution of constraints.
