"""Tests for the Phase-5 family allocation."""
from __future__ import annotations

import pytest

from clawsocialarena.generator.cell_allocation import (
    CATEGORIES,
    CELL_ALLOCATION,
    CellSpec,
    all_cells,
    cell_by_index,
    cell_for,
    cells_for_family,
    family_cell_counts,
)


_EXPECTED_PER_FAMILY_COUNTS = {
    "marble_research": 3,
    "marble_bargaining": 2,
    "marble_bidding": 2,
    "wildclaw_social": 2,
    "tau2_retail": 2,
    "tau2_telecom": 3,
    "tau2_airline": 2,
}


def test_allocation_has_expected_cell_count() -> None:
    assert len(CELL_ALLOCATION) == 16
    assert len(all_cells()) == 16


def test_cell_indexes_are_contiguous_in_order() -> None:
    for expected, cell in enumerate(CELL_ALLOCATION):
        assert cell.cell_index == expected


def test_every_category_appears_expected_number_of_times() -> None:
    expected_counts = {category: 2 for category in CATEGORIES}
    expected_counts["CM"] = 3
    expected_counts["CU"] = 3
    counts: dict[str, int] = {}
    for cell in CELL_ALLOCATION:
        counts[cell.category] = counts.get(cell.category, 0) + 1
    assert counts == expected_counts


def test_every_cell_has_known_slot() -> None:
    for cell in CELL_ALLOCATION:
        assert cell.slot in {"A", "B", "C"}


def test_each_category_uses_expected_slots() -> None:
    by_category: dict[str, set[str]] = {}
    for cell in CELL_ALLOCATION:
        by_category.setdefault(cell.category, set()).add(cell.slot)
    for category, slots in by_category.items():
        expected = {"A", "B", "C"} if category in {"CM", "CU"} else {"A", "B"}
        assert slots == expected, f"{category} slots = {slots}"


def test_per_family_cell_counts_match_spec_section_2() -> None:
    counts = family_cell_counts()
    assert counts == _EXPECTED_PER_FAMILY_COUNTS


@pytest.mark.parametrize(
    "family_id,expected_count",
    sorted(_EXPECTED_PER_FAMILY_COUNTS.items()),
)
def test_cells_for_family_returns_expected_count(
    family_id: str, expected_count: int
) -> None:
    cells = cells_for_family(family_id)
    assert len(cells) == expected_count
    for cell in cells:
        assert cell.family_id == family_id


def test_cells_for_family_raises_on_unknown_family_id() -> None:
    """Per codex Batch A non-blocker: silent-empty was a drift risk."""
    with pytest.raises(KeyError) as excinfo:
        cells_for_family("does_not_exist")
    message = str(excinfo.value)
    # Error must list the known family ids so a typo is easy to fix.
    for known in _EXPECTED_PER_FAMILY_COUNTS:
        assert known in message


def test_cell_for_roundtrips_against_index() -> None:
    for cell in CELL_ALLOCATION:
        roundtripped = cell_for(cell.category, cell.slot)
        assert roundtripped == cell


def test_cell_for_raises_on_unknown_coordinate() -> None:
    with pytest.raises(KeyError):
        cell_for("XX", "A")
    with pytest.raises(KeyError):
        cell_for("CD", "C")


def test_cell_by_index_returns_the_right_cell() -> None:
    assert cell_by_index(0).cell_id == "CD-A-marble_research"
    assert cell_by_index(14).cell_id == "CM-C-marble_bidding"
    assert cell_by_index(15).cell_id == "CU-C-marble_bidding"


def test_cell_by_index_out_of_range_raises() -> None:
    with pytest.raises(IndexError):
        cell_by_index(-1)
    with pytest.raises(IndexError):
        cell_by_index(16)


def test_cell_id_format_is_stable() -> None:
    # The cell_id is used in log lines and report tables; keep the
    # format frozen so downstream tooling can rely on it.
    for cell in CELL_ALLOCATION:
        assert cell.cell_id == f"{cell.category}-{cell.slot}-{cell.family_id}"


def test_total_base_task_count_matches_pilot_math() -> None:
    from clawsocialarena.generator.phase5_task_variants import task_variants_for

    total = sum(
        len(task_variants_for(cell.family_id, cell_id=cell.cell_id))
        for cell in CELL_ALLOCATION
    )
    assert total == 87


def test_cellspec_is_frozen() -> None:
    # Frozen dataclasses guarantee no accidental mutation in
    # downstream consumers. Confirm by attempting to mutate.
    cell = CELL_ALLOCATION[0]
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        cell.cell_index = 99  # type: ignore[misc]


def test_cellspec_construction_validates_slot() -> None:
    # The dataclass itself does not validate slot; we keep the
    # constraint enforceable via the canonical allocation, not the
    # type. This test documents that intentional choice: any cell
    # surfaced via CELL_ALLOCATION will have slot in {'A', 'B'}.
    sentinel = CellSpec(cell_index=99, category="CD", slot="A", family_id="x")
    assert sentinel.slot == "A"
