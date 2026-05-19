"""Tests for the Phase-5 supplementary stratum descriptors (S3 step 6)."""
from __future__ import annotations

from collections import Counter

from clawsocialarena.generator.family_pack_registry import FAMILY_LOADERS
from clawsocialarena.generator.phase5_supplementary import (
    EPISODE_GRAPH_COUNT,
    HARD_VERIFICATION_COUNT,
    NAMED_AUDIT_COUNT,
    SUB_STRATA,
    SUPPLEMENTARY_TOTAL,
    SupplementaryRecord,
    supplementary_records,
    supplementary_sub_counts,
)


def test_supplementary_total_is_fifty_eight() -> None:
    assert SUPPLEMENTARY_TOTAL == 58
    assert (
        HARD_VERIFICATION_COUNT + EPISODE_GRAPH_COUNT + NAMED_AUDIT_COUNT
        == SUPPLEMENTARY_TOTAL
    )


def test_supplementary_records_returns_58_records() -> None:
    records = supplementary_records()
    assert len(records) == 58
    assert all(isinstance(r, SupplementaryRecord) for r in records)


def test_supplementary_sub_counts_match_actual_records() -> None:
    records = supplementary_records()
    by_stratum = Counter(r.sub_stratum for r in records)
    assert dict(by_stratum) == supplementary_sub_counts()
    # Sub-strata must be from the declared set.
    assert set(by_stratum.keys()) == set(SUB_STRATA)


def test_supplementary_variant_ids_are_unique() -> None:
    records = supplementary_records()
    ids = [r.variant_id for r in records]
    assert len(set(ids)) == len(ids)


def test_episode_graph_records_form_seven_graphs_of_four_episodes() -> None:
    records = supplementary_records()
    graph_to_episodes: dict[int, set[int]] = {}
    for record in records:
        if record.sub_stratum != "episode_graph":
            continue
        params = record.parameters
        graph_to_episodes.setdefault(params["graph_index"], set()).add(
            params["episode_index"]
        )
    assert len(graph_to_episodes) == 7
    for graph_idx, episodes in graph_to_episodes.items():
        assert episodes == {0, 1, 2, 3}, (
            f"graph {graph_idx} has episodes {episodes}"
        )


def test_episode_graph_families_are_in_registry() -> None:
    records = supplementary_records()
    for record in records:
        if record.sub_stratum != "episode_graph":
            continue
        assert record.family_id in FAMILY_LOADERS, (
            f"episode_graph row {record.variant_id} references "
            f"unknown family_id={record.family_id!r}"
        )


def test_named_audit_records_target_distinct_failure_modes() -> None:
    records = supplementary_records()
    named = [r for r in records if r.sub_stratum == "named_audit"]
    assert len(named) == NAMED_AUDIT_COUNT
    failure_ids = [r.parameters["failure_id"] for r in named]
    assert len(set(failure_ids)) == len(failure_ids)


def test_hard_verification_split_is_twelve_code_thirteen_doc() -> None:
    records = supplementary_records()
    hv = [r for r in records if r.sub_stratum == "hard_verification"]
    code = [r for r in hv if r.recipe == "HardCodeReviewTemplate"]
    doc = [r for r in hv if r.recipe == "HardDocEditingTemplate"]
    assert len(code) == 12
    assert len(doc) == 13
