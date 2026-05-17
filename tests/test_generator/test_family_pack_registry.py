"""Tests for the family pack registry (Phase 5 Batch A)."""
from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.generator.family_pack_registry import (
    FAMILY_LOADERS,
    FamilyPackEntry,
    get_entry,
    load_and_materialize,
)


_EXPECTED_FAMILY_IDS = {
    "tau2_retail",
    "tau2_airline",
    "tau2_telecom",
    "marble_research",
    "marble_bargaining",
    "travel",
    "wildclaw_social",
}


def test_registry_covers_all_family_ids() -> None:
    assert set(FAMILY_LOADERS.keys()) == _EXPECTED_FAMILY_IDS


def test_every_entry_carries_required_fields() -> None:
    for family_id, entry in FAMILY_LOADERS.items():
        assert isinstance(entry, FamilyPackEntry)
        assert entry.family_id == family_id
        assert callable(entry.load_fn)
        assert callable(entry.materialize_fn)
        assert entry.session_context_keys, f"{family_id} has empty context keys"


def test_get_entry_returns_correct_entry() -> None:
    entry = get_entry("tau2_retail")
    assert entry.family_id == "tau2_retail"


def test_get_entry_raises_on_unknown_family_id() -> None:
    with pytest.raises(KeyError) as excinfo:
        get_entry("does_not_exist")
    # The error should list the known ids so callers can fix typos.
    message = str(excinfo.value)
    for family_id in _EXPECTED_FAMILY_IDS:
        assert family_id in message


@pytest.mark.parametrize("family_id", sorted(_EXPECTED_FAMILY_IDS))
def test_load_and_materialize_produces_a_bundle_dir(
    family_id: str,
    tmp_path: Path,
) -> None:
    bundle_dir, bundle = load_and_materialize(
        family_id=family_id,
        out_dir=tmp_path / family_id,
    )
    assert bundle_dir.is_dir()
    # Every pack must drop these top-level artifacts so the rest of
    # the pipeline can consume the bundle uniformly.
    assert (bundle_dir / "scenario.json").is_file()
    assert (bundle_dir / "scenario.gt.json").is_file()
    assert (bundle_dir / "family_pack_context.json").is_file()
    assert (bundle_dir / "docker-compose.yml").is_file()
    # The bundle object must expose a scenario with the right family_id.
    assert bundle.scenario.family_id == family_id


def test_load_and_materialize_forwards_load_kwargs(tmp_path: Path) -> None:
    bundle_dir, bundle = load_and_materialize(
        family_id="tau2_retail",
        out_dir=tmp_path / "retail",
        load_kwargs={"household_id": "HH-PHASE5"},
    )
    assert bundle.scenario.initial_state["household_id"] == "HH-PHASE5"


def test_session_context_keys_are_strings() -> None:
    for entry in FAMILY_LOADERS.values():
        for key in entry.session_context_keys:
            assert isinstance(key, str)
            assert key, f"{entry.family_id} has an empty context key"
