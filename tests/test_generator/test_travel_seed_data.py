"""Tests for the travel family pack seed schema (Task 2 of the travel plan)."""
from __future__ import annotations

import pytest

from clawsocialarena.generator.family_packs.travel.seed_data.travel_seeds import (
    TRAVEL_CU_TASK_SEEDS,
    TRAVEL_MG_TASK_SEEDS,
    TRAVEL_TASK_SEEDS,
    TravelTaskSeed,
    travel_task_seeds_for_cell,
)
from clawsocialarena.generator.family_packs.travel.seed_data import (
    load_travelbench_lifts,
)


def test_travel_exposes_six_total_distinct_owned_tasks() -> None:
    seeds = TRAVEL_TASK_SEEDS
    assert len(seeds) == 6
    assert len({s.trip_id for s in seeds}) == 6
    assert len({s.resource_profile for s in seeds}) == 6


def test_travel_cell_slices_are_three_distinct_tasks() -> None:
    cu = travel_task_seeds_for_cell("CU-D-travel")
    mg = travel_task_seeds_for_cell("MG-C-travel")
    assert len(cu) == 3
    assert len(mg) == 3
    assert {s.trip_id for s in cu}.isdisjoint({s.trip_id for s in mg})
    assert all(s.cell_id == "CU-D-travel" for s in cu)
    assert all(s.cell_id == "MG-C-travel" for s in mg)


def test_travel_task_seeds_for_cell_unknown_returns_full_pool() -> None:
    """Unknown / None cell_id returns every seed (used by audit listings)."""
    assert travel_task_seeds_for_cell(None) == TRAVEL_TASK_SEEDS
    assert travel_task_seeds_for_cell("not-a-cell") == TRAVEL_TASK_SEEDS


def test_mg_seeds_carry_group_pack_context() -> None:
    mg = travel_task_seeds_for_cell("MG-C-travel")
    for seed in mg:
        assert len(seed.co_traveler_lift_ids) == 3
        assert seed.group_budget_envelope is not None
        assert seed.per_person_cap is not None
        assert seed.consensus_threshold is not None
        # Co-traveler lifts must reference real lift_ids
        all_lift_ids = {lift.lift_id for lift in load_travelbench_lifts()}
        for clift in seed.co_traveler_lift_ids:
            assert clift in all_lift_ids, f"unknown co_traveler_lift_id {clift!r}"
        # Organizer should not also appear in their own co_traveler list
        assert seed.lift_id not in seed.co_traveler_lift_ids


def test_cu_seeds_have_no_group_pack_context() -> None:
    cu = travel_task_seeds_for_cell("CU-D-travel")
    for seed in cu:
        assert seed.co_traveler_lift_ids == ()
        assert seed.group_budget_envelope is None
        assert seed.per_person_cap is None
        assert seed.consensus_threshold is None


def test_every_seed_references_a_real_lift() -> None:
    """Each seed's lift_id must resolve to an actual TravelBench lift."""
    all_lift_ids = {lift.lift_id for lift in load_travelbench_lifts()}
    for seed in TRAVEL_TASK_SEEDS:
        assert seed.lift_id in all_lift_ids, (
            f"seed {seed.trip_id!r} references unknown lift_id {seed.lift_id!r}"
        )


def test_seed_cell_targets_match_lift_cell_targets() -> None:
    """A CU-D-travel seed must reference a CU-D-travel lift (its organizer);
    co_traveler lifts in MG seeds may reference any lift in the pool."""
    lift_by_id = {lift.lift_id: lift for lift in load_travelbench_lifts()}
    for seed in TRAVEL_CU_TASK_SEEDS:
        organizer_lift = lift_by_id[seed.lift_id]
        assert organizer_lift.cell_target == "CU-D-travel"
    for seed in TRAVEL_MG_TASK_SEEDS:
        organizer_lift = lift_by_id[seed.lift_id]
        assert organizer_lift.cell_target == "MG-C-travel"


def test_delegate_authorization_code_unique_per_trip() -> None:
    codes = [s.delegate_authorization_code for s in TRAVEL_TASK_SEEDS]
    assert len(codes) == len(set(codes))
    for code in codes:
        # Codes must include the trip id so they cannot be reused across trips
        # (matches the bargaining PRINTER-BUNDLE-12-DELEGATE-AUTH pattern).
        assert "DELEGATE-AUTH" in code


def test_partner_floor_rate_below_target_unit_rate() -> None:
    """The partner's reservation must leave a non-empty bargaining zone
    so the negotiation can converge (mirrors marble_bargaining)."""
    for seed in TRAVEL_TASK_SEEDS:
        assert seed.partner_floor_rate < seed.target_unit_rate


def test_seeds_are_deterministic() -> None:
    """Loading the seeds twice must produce identical tuples (frozen)."""
    a = travel_task_seeds_for_cell("CU-D-travel")
    b = travel_task_seeds_for_cell("CU-D-travel")
    assert a == b
    with pytest.raises(Exception):
        a[0].trip_id = "X"  # type: ignore[misc]
