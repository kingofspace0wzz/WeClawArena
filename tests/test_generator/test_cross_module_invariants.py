"""Cross-module invariants tying registry, cell allocation, and session dispatch.

Per codex's Batch A non-blocker recommendation: keep allocation ids,
registry ids, and Session.register_family_pack_tools dispatch branches
aligned. A drift here would let a later batch under-generate work or
fail silently. These invariants run as ordinary unit tests so any
divergence breaks CI at the source.
"""
from __future__ import annotations

import inspect
import re

from clawsocialarena.gateway import session as session_module
from clawsocialarena.generator.cell_allocation import CELL_ALLOCATION
from clawsocialarena.generator.family_pack_registry import FAMILY_LOADERS


def test_every_cell_family_id_is_in_registry() -> None:
    cell_family_ids = {cell.family_id for cell in CELL_ALLOCATION}
    registry_ids = set(FAMILY_LOADERS.keys())
    missing = cell_family_ids - registry_ids
    assert not missing, (
        f"cells reference family_ids absent from registry: {missing}"
    )


def test_every_registry_family_id_is_used_by_at_least_one_cell() -> None:
    """The allocation must exercise every pack -- if a pack ships but no
    cell uses it, either the spec drifted or the pack is dead code.
    """
    cell_family_ids = {cell.family_id for cell in CELL_ALLOCATION}
    registry_ids = set(FAMILY_LOADERS.keys())
    unused = registry_ids - cell_family_ids
    assert not unused, f"registered packs with no cell allocation: {unused}"


def test_session_dispatch_branches_cover_every_registry_family_id() -> None:
    """``Session.register_family_pack_tools`` must have an explicit
    dispatch branch for every registered family. We discover the
    branches by source inspection so a missing branch breaks this
    test immediately."""
    source = inspect.getsource(session_module.Session.register_family_pack_tools)
    # Match patterns like:  if family_id == "tau2_retail":
    pattern = re.compile(
        r"family_id\s*==\s*[\"']([a-z0-9_]+)[\"']", re.MULTILINE
    )
    dispatched_ids = set(pattern.findall(source))
    registry_ids = set(FAMILY_LOADERS.keys())
    missing = registry_ids - dispatched_ids
    assert not missing, (
        f"Session.register_family_pack_tools has no branch for: {missing}; "
        f"found branches: {sorted(dispatched_ids)}"
    )


def test_session_dispatch_does_not_carry_orphan_family_ids() -> None:
    """Every dispatch branch must map to a known registry id (the
    reverse of the previous test).
    """
    source = inspect.getsource(session_module.Session.register_family_pack_tools)
    pattern = re.compile(
        r"family_id\s*==\s*[\"']([a-z0-9_]+)[\"']", re.MULTILINE
    )
    dispatched_ids = set(pattern.findall(source))
    registry_ids = set(FAMILY_LOADERS.keys())
    orphans = dispatched_ids - registry_ids
    assert not orphans, (
        f"Session.register_family_pack_tools dispatches family_ids not in "
        f"the registry: {orphans}"
    )


def test_every_registry_entry_carries_naturalization_hints() -> None:
    """Phase-5 S2 contract: every registered pack must surface
    naturalization hints. The skeleton builder relies on this.
    """
    for family_id, entry in FAMILY_LOADERS.items():
        hints = entry.naturalization_hints
        assert isinstance(hints, dict), f"{family_id} hints is not a dict"
        for required_key in ("domain", "tone", "key_terms", "naturalization_focus"):
            assert required_key in hints, (
                f"{family_id} naturalization_hints missing '{required_key}'"
            )
        assert hints["domain"], f"{family_id} domain is empty"
        assert hints["naturalization_focus"], (
            f"{family_id} naturalization_focus is empty"
        )
        assert hints["key_terms"], f"{family_id} key_terms is empty"


def test_every_registry_entry_lists_session_context_keys() -> None:
    """Phase-5 generators populate session context per pack using these
    keys. A missing key would cause a silent default-fallback at
    Session.build time.
    """
    for family_id, entry in FAMILY_LOADERS.items():
        assert entry.session_context_keys, (
            f"{family_id} has empty session_context_keys"
        )
        for key in entry.session_context_keys:
            assert isinstance(key, str) and key, (
                f"{family_id} has a non-string or empty context key"
            )
