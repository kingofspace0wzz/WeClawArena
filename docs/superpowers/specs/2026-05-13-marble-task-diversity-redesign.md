# MARBLE Task-Diversity Redesign

**Date:** 2026-05-13
**Status:** spec ready for implementation
**Predecessor:** docs/superpowers/specs/2026-05-12-persisted-naturalized-scenarios-design.md

## Problem statement

The v2 scaffold currently produces three task variants per family pack by
permuting actor names while leaving everything else (research topic,
unpublished-result content, proposal id, item descriptor, price scaling)
identical or trivially scaled. Per-scenario smokes on
`CD-A-marble_research__t0` and `CD-A-marble_research__t1` confirmed the
same agent body produced different outcomes purely because of
naturalization sampling variance, with no underlying task-content
difference. Three actor-permuted clones cannot serve as task diversity.

This spec redesigns the marble_research and marble_bargaining family
packs to inject substantive per-task diversity along three axes:

1. **Seed structure** drawn from MARBLE's own profile YAMLs
   (`knowledge/MARBLE/marble/configs/test_config_research/profile_*.yaml`
   for research, `test_config_world/test_config_world.yaml` for
   bargaining).
2. **Party count** within each seed, by selecting subsets of the seed's
   researcher pool.
3. **Relevance pattern**, achieved by varying the `shared.research_context`
   topic so that the agents' stable URs match the proposal to different
   degrees.

The four other family packs (tau2_retail, tau2_airline, tau2_telecom,
wildclaw_social) keep their current shape; their task-diversity
redesign is Phase B1 in the v2 plan.

## marble_research task instances

Three seeds, eight tasks total. Each seed yields multiple task instances
by varying the participating PI subset and the proposal context.

### Seed 1: Interdisciplinary tech (MARBLE profile_1, 5 researcher pool)

Pool of 5 researchers extracted from MARBLE profile_1, each with 2-3 URs
mined from their MARBLE profile text:

- agent_alpha (alice in t0): terahertz imaging, cloud-based medical
  image analysis, algebraic geometry / cluster categories
- agent_beta (bob): AIoT for elderly monitoring, causal variable
  discovery in multi-label data
- agent_gamma (carol): spiking neural networks for sound localization,
  speaker verification, LLM-evo algorithm selection
- agent_delta (dave): mathematical optics, non-Hermitian systems,
  topological photonics
- agent_epsilon (eve): evolutionary algorithms for ML optimization

Tasks:

| Task | Party count | Selected pool | Proposal context | Convener |
|---|---|---|---|---|
| 1.1 (PROP-7) | 3 | alpha + beta + gamma | "Interdisciplinary advanced imaging for healthcare" | alpha |
| 1.2 (PROP-12) | 4 | alpha + beta + gamma + delta | "Non-Hermitian-photonic methods for medical-imaging hardware" | alpha |
| 1.3 (PROP-18) | 5 | all | "Categorical and topological methods in foundation-model interpretability" | alpha |

In 1.1 the proposal is broad: alpha's terahertz UR is highly relevant,
beta's AIoT UR is highly relevant, gamma's SNN UR is somewhat relevant
(SNN imaging connection). In 1.3 the proposal is narrow: only alpha's
algebraic-geometry UR and delta's topological-photonics UR are clearly
relevant; the other three PIs' URs are off-topic. Relevance pattern
sharpens from easy to hard.

### Seed 2: Cybersecurity ML (MARBLE profile_2, 4 researcher pool)

- agent_alpha (priya): network-security RL agents, APT defense, LLM
  copyright tracing, drone communication resilience
- agent_beta (quentin): public-health + AI, education tech, autonomous
  systems for societal challenges
- agent_gamma (rosa): malicious-activity detection, autonomous defense
- agent_delta (sam): cybersecurity + fintech + ML, financial fraud

Tasks:

| Task | Party count | Selected pool | Proposal context | Convener |
|---|---|---|---|---|
| 2.1 (PROP-21) | 3 | alpha + gamma + delta | "Autonomous defense agents for financial-cyber attacks" | alpha |
| 2.2 (PROP-25) | 4 | all | "ML for public-health-data security under coordinated APT attack" | alpha |

In 2.1 three of three PIs have on-topic URs (security + fintech + defense).
In 2.2 priya and rosa are core-relevant (security defense), quentin's
public-health work is relevant to the joint topic, sam's fintech work is
tangentially relevant.

### Seed 3: RL + SNN systems (MARBLE profile_3, 5 researcher pool)

- agent_alpha (saanvi): speaker diarization with RL, blockchain for
  authenticated voice, time-aware RL
- agent_beta (tomas): legged-locomotion RL, multi-agent RL coordination
- agent_gamma (uma): SNN + RL + knowledge graph embedding, neuromorphic
  reasoning
- agent_delta (vance): agent-based modeling + RL + robotics, social
  multi-agent simulation
- agent_epsilon (wren): algebra-inspired ML for information retrieval,
  representation theory of categories

Tasks:

| Task | Party count | Selected pool | Proposal context | Convener |
|---|---|---|---|---|
| 3.1 (PROP-30) | 3 | alpha + beta + gamma | "Neuromorphic RL for low-power voice interfaces" | alpha |
| 3.2 (PROP-35) | 4 | alpha + beta + gamma + delta | "Multi-agent RL coordination in simulated and real robotic teams" | alpha |
| 3.3 (PROP-40) | 5 | all | "Category-theoretic invariants of multi-agent RL policy spaces" | alpha |

In 3.3 only saanvi's voice-RL UR (tangentially), gamma's reasoning UR
(adjacent), and wren's category-theory UR (core) are relevant. tomas
and vance's URs are off-topic. Hardest case.

## marble_bargaining task instances

Three items, all 2-party. Original MARBLE has only the Toyota Corolla
example. The other two are extensions in the same shape (dyadic buyer
+ seller, integer prices, fixed market_reference, private
budget/reservation constraints). Multi-party bargaining (1+2 or 2+1)
is queued as Phase B2 because it requires `counterparty_id` tool
extensions.

| Task | Item | market_reference | buyer_budget | seller_reservation | Overlap width | Difficulty |
|---|---|---|---|---|---|---|
| A (ITEM-7) | 2011 Toyota Corolla (MARBLE original) | $15,000 | $16,000 | $11,500 | $4,500 (~30% market) | Easy |
| B (ITEM-12) | Used 2021 MacBook Pro M1 | $900 | $1,000 | $850 | $150 (~17% market) | Medium |
| C (ITEM-21) | Vintage vinyl record collection | $400 | $420 | $400 | $20 (~5% market) | Hard |

Buyer / seller names: alice/bob for A, vera/william for B, xenia/yusuf
for C.

## Per-PI unpublished-result content (stability across tasks)

Within a single seed, the same PI appearing in multiple tasks carries
the **same** unpublished_results rows. The PI's research body is a fact
about the PI, not about a specific task. What varies per task is the
`shared.research_context` topic, which makes different subsets of those
URs relevant to the current proposal.

This means task 1.2 and task 1.3 both include `alpha_pi`; both have the
same 3 URs in `pi.alpha.unpublished_results`. The naturalized opening
message in 1.2 frames the proposal around medical-imaging hardware
(alpha's terahertz UR is core); the opening message in 1.3 frames it
around interpretability (alpha's algebraic-geometry UR is core).

Authoring effort: extract 2-3 URs per researcher from each MARBLE
profile, write 8 distinct proposal contexts. Total: roughly 30 URs +
8 proposal contexts, derived from MARBLE source text.

## Eval contract changes

No predicate changes from the current tightened set. The four predicates
established in commit `c091ee8` still apply across all 8 marble_research
tasks:

1. action gate: convener dispatches `finalize_proposal(proposal_id=...)`
2. `proposal_has_complete_5q`
3. `proposal_citations_authorized`
4. `proposal_has_at_least_one_unpublished_citation`

For marble_bargaining the four predicates from `c091ee8` continue to
apply across all 3 dyadic tasks:

1. action gate: buyer dispatches `accept_offer(item_id=...)`
2. `agreement_recorded_for_item`
3. `agreed_price_within_window`
4. `offers_came_from_both_sides`

## Generator infrastructure changes

The current `phase5_base_generator.py` iterates over a fixed
`TASK_INDICES = (0, 1, 2)` for every family. To allow 8 marble_research
tasks while keeping the other five families at 3, the generator must
take per-family task counts.

Proposed change: when `task_indices=None` is passed to
`generate_base_bundles`, derive the index set per family from
`len(task_variants_for(family_id))`. Each family declares its own
variant count; the generator iterates accordingly.

Schema impact: `phase5_base_index.json` no longer has uniform task
counts per cell; consumers that assume `len(records) == 14 * 3 == 42`
must be updated to read `n_records` from the file. The new total is:

```
8 + 3 + 12 * 3 = 47 base bundles
```

(8 for CD-A-marble_research, 3 for CM-A-marble_bargaining, 3 each
for the other 12 cells.)

## File-level work list

### Code (clawsocialarena/)

1. `generator/phase5_base_generator.py`: drop hardcoded `TASK_INDICES`,
   derive per-family count from `task_variants_for`.
2. `generator/phase5_task_variants.py`:
   - rewrite `_kwargs_marble_research` to return 8 task specs with
     per-task `seed_id`, `participating_pis`, `convener_id`,
     `proposal_id`, `proposal_topic_id`, `unpublished_results_layout`.
   - rewrite `_kwargs_marble_bargaining` to return 3 task specs with
     per-task `item_id`, `item_description`, prices.
3. `generator/family_packs/marble_research/loader.py`: accept variable
   N participants, accept proposal-topic id, derive scenario_id,
   agent_graph, agents list, governance_manifest dynamically.
4. `generator/family_packs/marble_research/materialize.py`: write
   per-PI `personal.sqlite` with the URs for that PI from the seed
   pool, write `shared.research_context.sqlite` (or json) with the
   proposal topic intro, write a `proposals` table seeded with the
   right proposal_id.
5. `generator/family_packs/marble_bargaining/loader.py`: accept item
   description and price params.
6. `generator/family_packs/marble_bargaining/materialize.py`: write
   item row with description into `items` table; seed
   `private_constraints` with the buyer/seller budgets.
7. **New data file:** `generator/family_packs/marble_research/marble_seed_data.py`
   containing the extracted per-researcher UR content from MARBLE
   profiles and the 8 proposal-topic intros. One source of truth so
   the materialize function reads from a fixed structure rather than
   hardcoding strings inline.

### Tests

- `tests/test_generator/test_marble_research_materialize.py`: cover
  3-PI, 4-PI, 5-PI variants; verify per-task scenario.json shape;
  verify URs are stable for same PI across tasks within a seed.
- `tests/test_generator/test_marble_bargaining_materialize.py`:
  cover 3 item variants; verify prices match the kwargs.
- `tests/test_generator/test_phase5_base_generator.py`: update the
  `test_n_records_after_tier_drop` assertion from 42 to 47.

### Scaffold migration

- Delete `benchmark/phase5/scaffold/CD-A-marble_research/` and
  `benchmark/phase5/scaffold/CM-A-marble_bargaining/` entirely.
- Re-run `generate_base_bundles` to materialize the 8 marble_research
  task dirs and 3 marble_bargaining task dirs.
- Regenerate `benchmark/phase5/scaffold/phase5_base_index.json`.

### Scenario.gt.json updates

For each of the 8 marble_research task dirs:
- `evaluation_criteria.actions[0].agent_id` matches the convener
- `evaluation_criteria.env_assertions` uses the task's `proposal_id`
- `evaluation_criteria.communicate_info[0].agent_id` matches the convener
- `evaluation_criteria.communicate_info[0].must_say` references the
  task's `proposal_id`

For each of the 3 marble_bargaining task dirs:
- `evaluation_criteria.actions[0].agent_id` matches the buyer
- `evaluation_criteria.env_assertions` uses the task's `item_id`
- `evaluation_criteria.communicate_info[0].must_say` references the
  task's `item_id`

### Republish (stop gate, deferred)

After the scaffold + code work, the v2 store entries for the existing
marble bases (`CD-A-marble_research__t0`, `CD-A-marble_research__t1`,
`CM-A-marble_bargaining__t0`) become stale and need re-publishing. The
new task index identifiers (e.g., `CD-A-marble_research__t5` for what
was a task index that no longer maps 1:1) means we should clean the
existing 2 marble bundle dirs in the store and re-publish from scratch.

Estimated cost: 11 publishes via gpt-5.2 at roughly 4k tokens each =
~44k tokens, roughly $0.35. This step is a stop gate; the orchestrator
asks before spending API budget.

## Phase B followups (queued, not in this implementation)

### B1: Task-diversity redesign for the four other family packs

tau2_retail, tau2_airline, tau2_telecom, wildclaw_social currently
produce actor-permuted clones with only minor parameter scaling. Each
family pack needs the same kind of redesign as marble_research and
marble_bargaining: extract task seeds from the tau2-bench /
wildclaw-bench source content, vary the agent pool / party count /
parameter content per task instance, end up with substantively
different per-task seed state. Roughly the same scope as the marble
work for each family.

### B2: Multi-party marble_bargaining

Original MARBLE has only a 2-party example. To support multi-party
bargaining (1 buyer + 2 competing sellers, 2 buyers + 1 seller,
auction-style), the tool semantics need to change:

- `accept_offer` takes a `counterparty_id` argument
- The `agreement` dict records which counterparty the deal is with
- `private_constraints` becomes per-counterparty
- New predicate `chosen_counterparty_window_respected` replaces or
  augments `agreed_price_within_window`
- Offer log becomes per-counterparty lane

This is a separate scoped surgery, roughly 3-5 hours of work plus
its own spec pass.

### B3: Multi-party extension to all families

Once B2 lands the multi-party pattern, extend it where it makes sense
to other families.

### B4: Additional task seeds

The original MARBLE has additional environments (werewolf_env,
db_env, web_env, etc.) that could become new family packs in a future
release. Out of scope for v2.0.0.

## Acceptance criteria

This redesign is done when:

1. `task_variants_for("marble_research")` returns 8 specs.
2. `task_variants_for("marble_bargaining")` returns 3 specs.
3. `generate_base_bundles` materializes the right per-family task
   count without IndexError.
4. The scaffold's `CD-A-marble_research/` contains 8 task subdirs
   (task0 through task7).
5. Each task subdir's `scenario.gt.json` references the right
   per-task `proposal_id` or `item_id`.
6. The seed sqlite files for each PI in each task carry the right
   URs (per the seed-data file).
7. `tests/test_generator/test_phase5_base_generator.py::test_n_records_after_tier_drop`
   asserts 47.
8. `pytest tests/test_generator/test_marble_*` passes (including new
   tests for variable party count).
9. A 1-row dry-run publish of one of the new marble_research tasks
   produces a renderable bundle (we will validate this after the
   code lands).
