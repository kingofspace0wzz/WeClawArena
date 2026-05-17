"""Tests for the TravelBench seed lifts (Task 1 of the travel first-ship plan)."""
from __future__ import annotations

from clawsocialarena.generator.family_packs.travel.seed_data import (
    load_travelbench_lifts,
)


def test_travelbench_lifts_have_six_records() -> None:
    lifts = load_travelbench_lifts()
    assert len(lifts) == 6
    assert {lift.cell_target for lift in lifts} == {"CU-D-travel", "MG-C-travel"}
    assert sum(1 for lift in lifts if lift.cell_target == "CU-D-travel") == 3
    assert sum(1 for lift in lifts if lift.cell_target == "MG-C-travel") == 3


def test_travelbench_lifts_are_english_only() -> None:
    """Every lifted field that the agent sees must be ASCII-only.

    The first travel ship uses the English stratum; a Chinese
    cross-lingual stratum is deferred per the family-pack spec.
    """
    lifts = load_travelbench_lifts()
    for lift in lifts:
        assert all(ord(c) < 128 for c in lift.query_text), (
            f"non-ASCII in query for {lift.lift_id}"
        )
        assert all(ord(c) < 128 for c in lift.intent_text), (
            f"non-ASCII in intent for {lift.lift_id}"
        )


def test_travelbench_lifts_source_fidelity_recorded() -> None:
    """Family-pack spec section 4.7 requires the sha256 of the original
    Chinese query so a reviewer can verify the translation against the
    source row in TravelBench."""
    lifts = load_travelbench_lifts()
    for lift in lifts:
        assert lift.source["file"] in {"multi_turn.jsonl", "single_turn.jsonl"}
        assert lift.source["trace_id"]
        assert lift.source["original_query_sha256"]
        # sha256 hex is 64 chars
        assert len(lift.source["original_query_sha256"]) == 64


def test_travelbench_lifts_user_profile_blocks_populated_for_mg() -> None:
    """MG-C-travel needs rich user_profile blocks because each co_traveler
    is seeded from a distinct lift with private constraints. CU-D-travel
    also benefits but the requirement is softer."""
    lifts = load_travelbench_lifts()
    mg_lifts = [l for l in lifts if l.cell_target == "MG-C-travel"]
    for lift in mg_lifts:
        assert lift.user_profile_blocks, f"empty user_profile_blocks for {lift.lift_id}"
        # At minimum every MG lift must carry demographics + at least one
        # preference axis the group-trip task can dispatch on
        assert "demographics" in lift.user_profile_blocks
        other_axes = set(lift.user_profile_blocks.keys()) - {"demographics"}
        assert other_axes, f"no preference axes for {lift.lift_id}"


def test_travelbench_lifts_have_location_context() -> None:
    """Every lift must carry a current/destination location so the
    travel scenario loader can populate current_trip_state.json."""
    lifts = load_travelbench_lifts()
    for lift in lifts:
        assert lift.context_block, f"empty context for {lift.lift_id}"
        # At minimum we need either a current city or a destination
        ctx = lift.context_block
        assert ctx.get("current_city") or ctx.get("trip_destination"), (
            f"no location anchor for {lift.lift_id}"
        )
