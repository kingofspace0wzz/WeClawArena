"""Tests for travel registration in the family pack registry (Task 6)."""
from __future__ import annotations

from clawsocialarena.generator.cell_allocation import cells_for_family
from clawsocialarena.generator.family_pack_registry import (
    FAMILY_LOADERS,
    FamilyPackEntry,
)


def test_travel_family_pack_is_registered() -> None:
    assert "travel" in FAMILY_LOADERS
    entry = FAMILY_LOADERS["travel"]
    assert isinstance(entry, FamilyPackEntry)
    assert entry.family_id == "travel"
    assert callable(entry.load_fn)
    assert callable(entry.materialize_fn)
    assert isinstance(entry.session_context_keys, tuple)
    assert isinstance(entry.naturalization_hints, dict)


def test_travel_session_context_keys_include_agent_and_owner_ids() -> None:
    entry = FAMILY_LOADERS["travel"]
    keys = set(entry.session_context_keys)
    required = {
        "trip_id",
        "resource_profile",
        "destination",
        "target_unit_rate",
        "partner_floor_rate",
        "traveler_owner_id",
        "traveler_agent_id",
        "partner_hotel_owner_id",
        "partner_hotel_agent_id",
        "approver_owner_id",
        "approver_agent_id",
        "organizer_owner_id",
        "organizer_agent_id",
        "co_traveler_owner_ids",
        "co_traveler_agent_ids",
        "delegate_authorization_code",
    }
    missing = required - keys
    assert not missing, f"missing session_context_keys: {missing}"


def test_travel_naturalization_hints_have_required_shape() -> None:
    entry = FAMILY_LOADERS["travel"]
    hints = entry.naturalization_hints
    assert set(hints.keys()) >= {
        "domain",
        "tone",
        "key_terms",
        "naturalization_focus",
    }
    assert isinstance(hints["key_terms"], list)
    assert hints["key_terms"], "key_terms must be non-empty"


def test_travel_cells_appear_in_cell_allocation() -> None:
    cells = cells_for_family("travel")
    assert len(cells) == 2
    cell_ids = {c.cell_id for c in cells}
    assert cell_ids == {"CU-D-travel", "MG-C-travel"}


def test_travel_module_imports_cleanly_from_registry() -> None:
    """Importing FAMILY_LOADERS must not raise; the travel pack must
    be importable as a side effect."""
    from clawsocialarena.generator.family_pack_registry import FAMILY_LOADERS as F
    assert "travel" in F


def test_task_variants_for_travel_dispatches_by_cell() -> None:
    from clawsocialarena.generator.phase5_task_variants import task_variants_for

    cu = task_variants_for("travel", cell_id="CU-D-travel")
    mg = task_variants_for("travel", cell_id="MG-C-travel")
    full = task_variants_for("travel")
    assert len(cu) == 3
    assert len(mg) == 3
    assert len(full) == 6
    assert {v.loader_kwargs["trip_id"] for v in cu}.isdisjoint(
        {v.loader_kwargs["trip_id"] for v in mg}
    )


def test_phase5_tool_module_table_includes_travel() -> None:
    from clawsocialarena.orchestrator.phase5_agent_loop import (
        _FAMILY_TOOL_MODULES,
    )
    assert "travel" in _FAMILY_TOOL_MODULES
    assert _FAMILY_TOOL_MODULES["travel"] == "clawsocialarena.mcp_tools.travel"
