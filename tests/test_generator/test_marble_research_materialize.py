"""Tests for the marble_research materializer.

Covers the 3-PI default (task 0) and verifies that:
- per-PI SQLite databases contain real seed URs (not placeholder text)
- UR content is stable: same owner across different tasks carries identical rows
- shared_research_context.json is written with topic intro and PI summaries
- scenario.gt.json carries all three evaluation predicates
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.generator.family_packs.marble_research import (
    load_research_collaboration_scenario,
    materialize_research_collaboration_bundle,
)
from clawsocialarena.generator.family_packs.marble_research.marble_seed_data import (
    ALL_TASKS,
    researcher_by_owner,
    seed_by_id,
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
        "shared_research_context.json",
        "docker-compose.yml",
    ):
        assert (bundle_dir / name).is_file(), f"missing {name}"


def test_per_pi_sqlite_has_proposal_and_real_urs(bundle_dir: Path) -> None:
    """The default 3-PI scenario (task 0: alpha, beta, gamma) must have
    per-PI SQLite files with the correct real URs from marble_seed_data.
    """
    seed = seed_by_id("interdisciplinary_tech")
    for owner in ("alpha", "beta", "gamma"):
        researcher = researcher_by_owner(seed, owner)
        db_path = bundle_dir / "resources" / "pis" / owner / "db" / "personal.sqlite"
        assert db_path.is_file(), f"missing SQLite for {owner}"
        with sqlite3.connect(db_path) as conn:
            proposals = list(conn.execute("SELECT proposal_id FROM proposals"))
            assert len(proposals) == 1
            assert proposals[0][0] == "PROP-7"
            results = list(
                conn.execute(
                    "SELECT result_id, owner_id, summary FROM unpublished_results"
                )
            )
            # Number of URs must match seed data (not a hardcoded 2).
            expected_count = len(researcher.unpublished_results)
            assert len(results) == expected_count, (
                f"{owner} should have {expected_count} URs, got {len(results)}"
            )
            for result_id, owner_id, summary in results:
                assert owner_id == owner
                # Summary must be non-trivial (not the old placeholder text).
                assert "benchmark X" not in summary
                assert len(summary) > 20


def test_ur_stability_across_tasks(tmp_path: Path) -> None:
    """alpha's URs must be identical in task 0 (3-PI) and task 1 (4-PI)
    because per-PI URs are seed-level, not task-level.
    """
    task0 = ALL_TASKS[0]  # seed=interdisciplinary_tech, alpha/beta/gamma
    task1 = ALL_TASKS[1]  # seed=interdisciplinary_tech, alpha/beta/gamma/delta

    def _alpha_urs_for_task(task: object, out_subdir: str) -> list[tuple]:
        bundle = load_research_collaboration_scenario(
            scenario_id=f"test_{out_subdir}",
            seed_id=task.seed_id,
            proposal_id=task.proposal_id,
            convener_owner=task.convener_owner,
            convener_id=f"{task.convener_owner}_pi",
            participating_owners=task.participating_owners,
            proposal_topic_title=task.proposal_topic_title,
            proposal_topic_intro=task.proposal_topic_intro,
        )
        materialize_research_collaboration_bundle(bundle, tmp_path / out_subdir)
        db_path = (
            tmp_path / out_subdir / "resources" / "pis" / "alpha" / "db" / "personal.sqlite"
        )
        with sqlite3.connect(db_path) as conn:
            return sorted(
                conn.execute(
                    "SELECT result_id, summary FROM unpublished_results"
                ).fetchall()
            )

    urs_task0 = _alpha_urs_for_task(task0, "t0")
    urs_task1 = _alpha_urs_for_task(task1, "t1")
    assert urs_task0 == urs_task1, (
        "alpha URs must be identical across tasks within the same seed"
    )


@pytest.mark.parametrize("task_index, expected_n_owners", [
    (0, 3),
    (1, 4),
    (2, 5),
])
def test_sqlite_per_owner_count_matches_task_spec(
    task_index: int,
    expected_n_owners: int,
    tmp_path: Path,
) -> None:
    """Each task must write exactly N SQLite files, one per participating owner."""
    task = ALL_TASKS[task_index]
    bundle = load_research_collaboration_scenario(
        scenario_id=f"marble_research_collaboration_phase5_v{task_index}",
        seed_id=task.seed_id,
        proposal_id=task.proposal_id,
        convener_owner=task.convener_owner,
        convener_id=f"{task.convener_owner}_pi",
        participating_owners=task.participating_owners,
        proposal_topic_title=task.proposal_topic_title,
        proposal_topic_intro=task.proposal_topic_intro,
    )
    out = tmp_path / f"task{task_index}"
    materialize_research_collaboration_bundle(bundle, out)
    sqlite_files = list((out / "resources" / "pis").glob("*/db/personal.sqlite"))
    assert len(sqlite_files) == expected_n_owners, (
        f"task {task_index} should produce {expected_n_owners} SQLite files"
    )


def test_family_pack_context_lists_peers(bundle_dir: Path) -> None:
    context = json.loads((bundle_dir / "family_pack_context.json").read_text())
    assert context["convener_owner_id"] == "alpha"
    assert set(context["peer_owner_ids"]) == {"beta", "gamma"}
    assert context["seed_id"] == "interdisciplinary_tech"


def test_shared_research_context_carries_topic_and_pi_summaries(
    bundle_dir: Path,
) -> None:
    shared = json.loads((bundle_dir / "shared_research_context.json").read_text())
    assert shared["proposal_id"] == "PROP-7"
    assert shared["seed_id"] == "interdisciplinary_tech"
    assert len(shared["participating_pis"]) == 3
    for pi in shared["participating_pis"]:
        assert pi["research_summary"]
        assert pi["owner_id"] in ("alpha", "beta", "gamma")


def test_compose_threads_family_pack_flags(bundle_dir: Path) -> None:
    compose_text = (bundle_dir / "docker-compose.yml").read_text()
    assert "marble_research" in compose_text
    assert "--family-pack-context-path" in compose_text


def test_gt_carries_all_three_evaluation_predicates(bundle_dir: Path) -> None:
    gt = json.loads((bundle_dir / "scenario.gt.json").read_text())
    predicates = {
        a["predicate"] for a in gt["evaluation_criteria"]["env_assertions"]
    }
    assert predicates == {
        "proposal_has_complete_5q",
        "proposal_citations_authorized",
        "proposal_has_at_least_one_unpublished_citation",
    }
