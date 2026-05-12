"""Tests for the marble_research materializer."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.generator.family_packs.marble_research import (
    load_research_collaboration_scenario,
    materialize_research_collaboration_bundle,
)


@pytest.fixture
def bundle_dir(tmp_path: Path) -> Path:
    bundle = load_research_collaboration_scenario()
    return materialize_research_collaboration_bundle(bundle, tmp_path / "scenario")


def test_writes_top_level_artifacts(bundle_dir: Path) -> None:
    for name in (
        "scenario.json",
        "scenario.gt.json",
        "family_pack_context.json",
        "docker-compose.yml",
    ):
        assert (bundle_dir / name).is_file(), f"missing {name}"


def test_per_pi_sqlite_has_proposal_and_unpublished_results(bundle_dir: Path) -> None:
    for owner in ("alice", "bob", "carol"):
        db_path = bundle_dir / "resources" / "pis" / owner / "db" / "personal.sqlite"
        assert db_path.is_file()
        with sqlite3.connect(db_path) as conn:
            proposals = list(conn.execute("SELECT proposal_id FROM proposals"))
            assert len(proposals) == 1
            assert proposals[0][0] == "PROP-7"
            results = list(
                conn.execute(
                    "SELECT result_id, owner_id FROM unpublished_results"
                )
            )
            assert len(results) == 2
            for _, owner_id in results:
                assert owner_id == owner


def test_family_pack_context_lists_peers(bundle_dir: Path) -> None:
    context = json.loads((bundle_dir / "family_pack_context.json").read_text())
    assert context["convener_owner_id"] == "alice"
    assert set(context["peer_owner_ids"]) == {"bob", "carol"}


def test_compose_threads_family_pack_flags(bundle_dir: Path) -> None:
    compose_text = (bundle_dir / "docker-compose.yml").read_text()
    assert "marble_research" in compose_text
    assert "--family-pack-context-path" in compose_text


def test_gt_carries_evaluation_criteria(bundle_dir: Path) -> None:
    gt = json.loads((bundle_dir / "scenario.gt.json").read_text())
    predicates = [
        a["predicate"] for a in gt["evaluation_criteria"]["env_assertions"]
    ]
    assert "proposal_has_complete_5q" in predicates
    assert "proposal_citations_authorized" in predicates
