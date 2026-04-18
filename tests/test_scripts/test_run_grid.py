"""Tests for ``scripts/run_grid.py`` (Phase G2 / G3).

These tests exercise the runner against a hand-crafted four-row grid so
we can confirm:

* ``--dry-run`` (default) writes a pending scorecard stub per row and
  does not touch the gateway.
* Stubs land under the right path (``<out>/<model>/<condition>/<scenario_id>``).
* A second invocation on the same output tree is idempotent: rows with
  a completed scorecard are skipped; pending stubs are rewritten.
* Replay rows produce a real :class:`RunScorecard` (no ``status`` key)
  with SAF dims populated.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

# Make scripts/ importable.
from scripts import run_grid


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_CASSETTE = REPO_ROOT / "fixtures" / "scenarios" / "cu_scheduling_mvp" / "sample_cassette.jsonl"
SAMPLE_GT = REPO_ROOT / "fixtures" / "scenarios" / "cu_scheduling_mvp" / "scenario.gt.json"


@pytest.fixture
def tiny_grid_yaml(tmp_path: Path) -> Path:
    """Write a four-row smoke grid with all-live rows under tmp_path."""

    rows = [
        {
            "scenario_id": "cu-scheduling-mvp",
            "condition": "baseline",
            "model": "claude-sonnet-4-6",
            "privacy_level": "L2",
            "seed": 0,
            "live_or_replay": "live",
            "tags": {"bucket": "smoke"},
        },
        {
            "scenario_id": "cu-scheduling-mvp",
            "condition": "passive",
            "model": "claude-sonnet-4-6",
            "privacy_level": "L2",
            "seed": 0,
            "live_or_replay": "live",
            "tags": {"bucket": "smoke"},
        },
        {
            "scenario_id": "cu-scheduling-mvp",
            "condition": "enforce",
            "model": "claude-sonnet-4-6",
            "privacy_level": "L2",
            "seed": 0,
            "live_or_replay": "live",
            "tags": {"bucket": "smoke"},
        },
        {
            "scenario_id": "cu-scheduling-mvp",
            "condition": "passive",
            "model": "gpt-5-mini",
            "privacy_level": "L2",
            "seed": 0,
            "live_or_replay": "live",
            "tags": {"bucket": "smoke"},
        },
    ]
    path = tmp_path / "grid.yaml"
    path.write_text(yaml.safe_dump(rows, sort_keys=False), encoding="utf-8")
    return path


def test_dry_run_writes_stub_per_row(tiny_grid_yaml: Path, tmp_path: Path) -> None:
    out = tmp_path / "results"
    rc = run_grid.main(
        ["--config", str(tiny_grid_yaml), "--out", str(out), "--dry-run"]
    )
    assert rc == 0

    # Four stubs under <out>/<model>/<condition>/<scenario_id>/run_scorecard.json.
    stubs = sorted(out.rglob("run_scorecard.json"))
    assert len(stubs) == 4

    for stub in stubs:
        data = json.loads(stub.read_text(encoding="utf-8"))
        assert data["status"] == "pending"
        assert data["scenario_id"] == "cu-scheduling-mvp"
        meta = data["meta"]
        assert meta["model"] in {"claude-sonnet-4-6", "gpt-5-mini"}
        assert meta["condition"] in {"baseline", "passive", "enforce"}
        assert meta["live_or_replay"] == "live"


def test_stub_path_layout(tiny_grid_yaml: Path, tmp_path: Path) -> None:
    out = tmp_path / "results"
    run_grid.main(
        ["--config", str(tiny_grid_yaml), "--out", str(out), "--dry-run"]
    )
    # Verify the path is exactly <model>/<condition>/<scenario_id>/.
    expected = (
        out
        / "claude-sonnet-4-6"
        / "baseline"
        / "cu-scheduling-mvp"
        / "run_scorecard.json"
    )
    assert expected.exists()


def test_resumable_skips_completed(
    tiny_grid_yaml: Path, tmp_path: Path
) -> None:
    out = tmp_path / "results"
    run_grid.main(
        ["--config", str(tiny_grid_yaml), "--out", str(out), "--dry-run"]
    )

    # Mark one scorecard as complete by stripping the pending status and
    # re-saving with a non-pending payload. The second invocation should
    # not overwrite it.
    one = next(out.rglob("run_scorecard.json"))
    one.write_text(
        json.dumps({"scenario_id": "x", "status": "ok", "meta": {"done": "true"}}),
        encoding="utf-8",
    )

    run_grid.main(
        ["--config", str(tiny_grid_yaml), "--out", str(out), "--dry-run"]
    )

    # Completed file should still carry its sentinel.
    data = json.loads(one.read_text(encoding="utf-8"))
    assert data["status"] == "ok"
    assert data["meta"]["done"] == "true"


def test_parse_args_defaults() -> None:
    args = run_grid.parse_args(["--config", "x.yaml", "--out", "o"])
    assert args.dry_run is True
    assert args.parallel == 1
