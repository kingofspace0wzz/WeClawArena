"""Tests for the swebench_workspace materializer."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.generator.family_packs.swebench_workspace import (
    load_workspace_coding_scenario,
    materialize_workspace_coding_bundle,
)


@pytest.fixture
def bundle_dir(tmp_path: Path) -> Path:
    bundle = load_workspace_coding_scenario()
    return materialize_workspace_coding_bundle(bundle, tmp_path / "scenario")


def test_workspace_materializer_writes_top_level_artifacts(bundle_dir: Path) -> None:
    for name in (
        "scenario.json",
        "scenario.gt.json",
        "family_pack_context.json",
        "docker-compose.yml",
        "phase5_metadata.json",
        "naturalization_record.json",
    ):
        assert (bundle_dir / name).is_file()


def test_workspace_materializer_writes_publish_sidecars(bundle_dir: Path) -> None:
    metadata = json.loads((bundle_dir / "phase5_metadata.json").read_text())
    assert metadata["base_id"] == "swebench_workspace_phase5_v0"
    assert metadata["family_id"] == "swebench_workspace"
    assert metadata["task_index"] == 0
    assert metadata["source"]["instance_id"] == "astropy__astropy-12907"
    assert metadata["task_variant"]["loader_kwargs"]["seed_id"]

    naturalization = json.loads(
        (bundle_dir / "naturalization_record.json").read_text()
    )
    assert naturalization["naturalization_model"] == "none"
    assert naturalization["status"] == "not_naturalized_review_approved_seed"


def test_workspace_materializer_writes_repo_and_policy_resources(
    bundle_dir: Path,
) -> None:
    metadata = json.loads(
        (bundle_dir / "resources" / "repo" / "metadata.json").read_text()
    )
    assert metadata["instance_id"] == "astropy__astropy-12907"
    assert metadata["source_dataset"] == "princeton-nlp/SWE-bench_Lite"
    assert "gold_patch" not in metadata
    assert (
        bundle_dir
        / "resources"
        / "repo"
        / "worktree"
        / "astropy"
        / "modeling"
        / "separable.py"
    ).is_file()
    assert (bundle_dir / "resources" / "team" / "ownership.json").is_file()
    assert (bundle_dir / "resources" / "team" / "review_policy.md").is_file()


def test_workspace_sqlite_seeds_run_state_for_each_owner(
    bundle_dir: Path,
) -> None:
    for owner in ("maya", "nolan", "opal", "priya"):
        db = bundle_dir / "resources" / "owners" / owner / "db" / "personal.sqlite"
        assert db.is_file()
        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT instance_id, patch_submitted, patch_applies, "
                "target_tests, required_approvals FROM workspace_runs "
                "WHERE instance_id = 'astropy__astropy-12907'",
            ).fetchone()
        assert row[0] == "astropy__astropy-12907"
        assert row[1] == 0
        assert row[2] == 0
        assert json.loads(row[3])[0]["passed"] is False
        assert json.loads(row[4])[0]["owner_id"] == "opal"


def test_workspace_materializer_writes_tool_stubs(bundle_dir: Path) -> None:
    for tool_name in (
        "repo.search",
        "repo.read",
        "repo.write",
        "repo.diff",
        "repo.run_tests",
        "repo.submit_patch",
        "review.approve",
        "policy.grant_approval",
    ):
        stub = bundle_dir / "mcp" / f"{tool_name}.json"
        assert stub.is_file()
        payload = json.loads(stub.read_text())
        assert payload["tool_name"] == tool_name
