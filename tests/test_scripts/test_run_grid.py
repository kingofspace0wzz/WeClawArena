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


@pytest.fixture
def replay_grid_yaml(tmp_path: Path) -> Path:
    """Single-row replay grid pointing at the fixture cassette."""

    rows = [
        {
            "scenario_id": "cu-scheduling-mvp",
            "condition": "passive",
            "model": "claude-sonnet-4-6",
            "privacy_level": "L2",
            "seed": 0,
            "live_or_replay": "replay",
            "cassette_path": str(SAMPLE_CASSETTE),
            "tags": {"bucket": "replay_smoke"},
        },
    ]
    path = tmp_path / "replay_grid.yaml"
    path.write_text(yaml.safe_dump(rows, sort_keys=False), encoding="utf-8")
    return path


def test_replay_row_writes_real_scorecard(
    replay_grid_yaml: Path, tmp_path: Path
) -> None:
    """Replay rows must produce a full RunScorecard, not a pending stub."""

    out = tmp_path / "results"
    rc = run_grid.main(
        ["--config", str(replay_grid_yaml), "--out", str(out)]
    )
    assert rc == 0

    scorecard_path = (
        out
        / "claude-sonnet-4-6"
        / "passive"
        / "cu-scheduling-mvp"
        / "run_scorecard.json"
    )
    assert scorecard_path.exists()

    data = json.loads(scorecard_path.read_text(encoding="utf-8"))
    # Real scorecard has no top-level "status" field (that only appears
    # on pending stubs). It must carry the six SAF dims + the runtime
    # provenance fields.
    assert "status" not in data
    assert data["scenario_id"] == "cu-scheduling-mvp"
    assert data["live_or_replay"] == "replay"
    saf = data["saf"]
    assert set(saf["dims"].keys()) == {
        "recoverability",
        "policy_checkability",
        "attribution",
        "evidence_integrity",
        "phase_scoped_policy",
        "identity_governance",
    }
    # cassette_hash is non-empty — we hashed the fixture file.
    assert data["cassette_hash"]
    # gateway_invariant_passed holds because replay re-computes hash chain.
    assert data["gateway_invariant_passed"] is True


def test_replay_row_is_resumable(
    replay_grid_yaml: Path, tmp_path: Path
) -> None:
    """A second invocation should skip the replay row once complete."""

    out = tmp_path / "results"
    run_grid.main(["--config", str(replay_grid_yaml), "--out", str(out)])
    scorecard_path = (
        out
        / "claude-sonnet-4-6"
        / "passive"
        / "cu-scheduling-mvp"
        / "run_scorecard.json"
    )
    first_mtime = scorecard_path.stat().st_mtime_ns

    # Run again; the completed scorecard should not be rewritten.
    run_grid.main(["--config", str(replay_grid_yaml), "--out", str(out)])
    assert scorecard_path.stat().st_mtime_ns == first_mtime


def test_replay_missing_cassette_reports_failure(
    tmp_path: Path,
) -> None:
    """A replay row pointing at a nonexistent cassette must be flagged."""

    rows = [
        {
            "scenario_id": "cu-scheduling-mvp",
            "condition": "passive",
            "model": "claude-sonnet-4-6",
            "privacy_level": "L2",
            "seed": 0,
            "live_or_replay": "replay",
            "cassette_path": str(tmp_path / "nope.jsonl"),
        },
    ]
    grid = tmp_path / "grid.yaml"
    grid.write_text(yaml.safe_dump(rows, sort_keys=False), encoding="utf-8")
    out = tmp_path / "out"
    rc = run_grid.main(["--config", str(grid), "--out", str(out)])
    # run() returns exit code 1 when any row fails.
    assert rc == 1
