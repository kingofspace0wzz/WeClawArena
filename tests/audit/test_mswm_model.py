"""Tests for the MSWM data model (Phase C / Task C1)."""

from __future__ import annotations

from clawsocialarena.audit.mswm import MSWM, PeerModel


def test_mswm_instantiates_empty() -> None:
    mswm = MSWM()
    assert mswm.state == {}
    assert list(mswm.pairs()) == []


def test_get_returns_default_peer_model() -> None:
    mswm = MSWM()
    model = mswm.get("alice", "bob")
    assert isinstance(model, PeerModel)
    assert model.items_told_to_j == set()
    assert model.items_learned_from_j == set()
    assert model.commitments_to_j == set()
    assert model.phase_of_last_interaction is None
    assert model.trust_estimate == 0.5


def test_get_is_idempotent_returns_same_instance() -> None:
    mswm = MSWM()
    first = mswm.get("alice", "bob")
    first.items_told_to_j.add(("z", "act-1"))
    second = mswm.get("alice", "bob")
    assert second is first
    assert ("z", "act-1") in second.items_told_to_j


def test_pairs_iterates_present_edges() -> None:
    mswm = MSWM()
    mswm.get("alice", "bob")
    mswm.get("alice", "carol")
    mswm.get("bob", "alice")
    pairs = set(mswm.pairs())
    assert pairs == {("alice", "bob"), ("alice", "carol"), ("bob", "alice")}


def test_peer_model_independent_sets() -> None:
    """Default-factory sets must not be shared across PeerModel instances."""
    mswm = MSWM()
    a = mswm.get("alice", "bob")
    b = mswm.get("alice", "carol")
    a.items_told_to_j.add(("x", "act-1"))
    assert ("x", "act-1") not in b.items_told_to_j
