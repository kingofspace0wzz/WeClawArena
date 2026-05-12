"""14-cell × family allocation for the Phase-5 pilot.

Encodes the table from
``docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md``
section 2 ("Family-to-Category Allocation (Default A)") as a single
canonical structure.

The pilot math is:

    14 cells x 3 base tasks x 3 difficulty tiers = 126 base tasks
    x 5 attack modes per base task                = 630 matched variants
    + 50 supplementary scenarios                  = 680 pilot variants

Every category (CD/MC/CU/MG/HS/CM/AM) appears in exactly two cells,
with one cell per family slot ("A" or "B"). Per-family cell counts
sum to 14 (marble_research 3, marble_bargaining 2, wildclaw_social 2,
tau2_retail 2, tau2_telecom 3, tau2_airline 2).
"""
from __future__ import annotations

from dataclasses import dataclass


CATEGORIES: tuple[str, ...] = ("CD", "MC", "CU", "MG", "HS", "CM", "AM")


@dataclass(frozen=True)
class CellSpec:
    """One cell of the 14-cell pilot allocation.

    ``cell_index`` is the canonical 0..13 ordering used by the
    Phase-5 generator's deterministic seeding so a single integer
    uniquely identifies a cell across logs / reports.
    """

    cell_index: int
    category: str
    slot: str  # "A" or "B"
    family_id: str

    @property
    def cell_id(self) -> str:
        """Stable string label, e.g. 'CD-A-marble_research'."""
        return f"{self.category}-{self.slot}-{self.family_id}"


CELL_ALLOCATION: tuple[CellSpec, ...] = (
    CellSpec(0, "CD", "A", "marble_research"),
    CellSpec(1, "CD", "B", "tau2_airline"),
    CellSpec(2, "MC", "A", "wildclaw_social"),
    CellSpec(3, "MC", "B", "tau2_airline"),
    CellSpec(4, "CU", "A", "marble_bargaining"),
    CellSpec(5, "CU", "B", "tau2_retail"),
    CellSpec(6, "MG", "A", "tau2_telecom"),
    CellSpec(7, "MG", "B", "marble_research"),
    CellSpec(8, "HS", "A", "marble_research"),
    CellSpec(9, "HS", "B", "tau2_telecom"),
    CellSpec(10, "CM", "A", "marble_bargaining"),
    CellSpec(11, "CM", "B", "wildclaw_social"),
    CellSpec(12, "AM", "A", "tau2_retail"),
    CellSpec(13, "AM", "B", "tau2_telecom"),
)


def all_cells() -> tuple[CellSpec, ...]:
    """Return every cell in canonical order."""
    return CELL_ALLOCATION


def cells_for_family(family_id: str) -> tuple[CellSpec, ...]:
    """Return every cell that uses ``family_id`` (in cell_index order).

    Raises ``KeyError`` for an unknown ``family_id`` so a downstream
    typo fails fast at the registry boundary instead of silently
    returning an empty tuple and under-generating work. The known
    family ids are listed in the error message.
    """
    known_ids = {cell.family_id for cell in CELL_ALLOCATION}
    if family_id not in known_ids:
        raise KeyError(
            f"unknown family_id={family_id!r}; "
            f"cells reference: {sorted(known_ids)}"
        )
    return tuple(cell for cell in CELL_ALLOCATION if cell.family_id == family_id)


def cell_for(category: str, slot: str) -> CellSpec:
    """Return the cell at the (category, slot) coordinate or raise.

    Categories and slots are case-sensitive; the error message lists
    the supported categories so a typo is easy to diagnose.
    """
    for cell in CELL_ALLOCATION:
        if cell.category == category and cell.slot == slot:
            return cell
    raise KeyError(
        f"no cell at category={category!r} slot={slot!r}; "
        f"categories={CATEGORIES} slots=('A', 'B')"
    )


def cell_by_index(cell_index: int) -> CellSpec:
    """Return the cell at the 0..13 canonical index or raise IndexError."""
    if not 0 <= cell_index < len(CELL_ALLOCATION):
        raise IndexError(
            f"cell_index {cell_index} out of range [0, {len(CELL_ALLOCATION)})"
        )
    return CELL_ALLOCATION[cell_index]


def family_cell_counts() -> dict[str, int]:
    """Return ``{family_id: count_of_cells}`` for the allocation.

    Used by the Phase-5 acceptance check to confirm the per-family
    cell totals match the spec section 2 table.
    """
    counts: dict[str, int] = {}
    for cell in CELL_ALLOCATION:
        counts[cell.family_id] = counts.get(cell.family_id, 0) + 1
    return counts
