"""Tests for the Phase G grid-config loader.

Exercises the two shipped sample YAMLs (``configs/main_table.yaml`` and
``configs/ablations.yaml``) plus a handful of synthetic bad inputs to
confirm the validator rejects malformed rows at load time instead of
leaking them to the batch runner.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clawsocialarena.experiments.grid_config import GridRow, load_grid
from clawsocialarena.types import AuditCondition


REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_TABLE = REPO_ROOT / "configs" / "main_table.yaml"
ABLATIONS = REPO_ROOT / "configs" / "ablations.yaml"


def test_main_table_sample_loads() -> None:
    rows = load_grid(MAIN_TABLE)
    # Sample carries four rows per the pre-populated smoke grid.
    assert len(rows) == 4
    # Typed enum on condition and Literal on live_or_replay.
    conditions = {r.condition for r in rows}
    assert conditions == {
        AuditCondition.BASELINE,
        AuditCondition.PASSIVE,
        AuditCondition.ENFORCE,
    }
    lor = {r.live_or_replay for r in rows}
    assert lor == {"live", "replay"}
    # Replay rows must carry a cassette path.
    for r in rows:
        if r.live_or_replay == "replay":
            assert isinstance(r.cassette_path, Path)
        # Tags propagate through as a plain str->str mapping.
        assert isinstance(r.tags, dict)


def test_ablations_sample_loads() -> None:
    rows = load_grid(ABLATIONS)
    assert len(rows) == 4
    # All ablation rows are replays (spec §5.4 ablations bucket).
    assert all(r.live_or_replay == "replay" for r in rows)
    # Privacy ladder covers the extremes plus mid-level.
    assert {r.privacy_level for r in rows}.issuperset({"L0", "L4"})
    # Strata tag: privacy_ladder + two external-baseline cells.
    strata = {r.tags.get("stratum") for r in rows}
    assert "privacy_ladder" in strata
    assert any(s and s.startswith("external_baseline") for s in strata)


def test_missing_field_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "- scenario_id: x\n"
        "  # condition omitted\n"
        "  model: m\n"
        "  privacy_level: L2\n"
        "  seed: 0\n"
        "  live_or_replay: live\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="condition"):
        load_grid(bad)


def test_bad_condition_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "- scenario_id: x\n"
        "  condition: hybrid\n"
        "  model: m\n"
        "  privacy_level: L2\n"
        "  seed: 0\n"
        "  live_or_replay: live\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="condition"):
        load_grid(bad)


def test_negative_seed_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "- scenario_id: x\n"
        "  condition: passive\n"
        "  model: m\n"
        "  privacy_level: L2\n"
        "  seed: -1\n"
        "  live_or_replay: live\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non-negative"):
        load_grid(bad)


def test_replay_without_cassette_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "- scenario_id: x\n"
        "  condition: passive\n"
        "  model: m\n"
        "  privacy_level: L2\n"
        "  seed: 0\n"
        "  live_or_replay: replay\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="cassette_path"):
        load_grid(bad)


def test_bad_live_or_replay_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "- scenario_id: x\n"
        "  condition: passive\n"
        "  model: m\n"
        "  privacy_level: L2\n"
        "  seed: 0\n"
        "  live_or_replay: dryrun\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="live_or_replay"):
        load_grid(bad)


def test_top_level_must_be_list(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("scenario_id: x\ncondition: passive\n", encoding="utf-8")
    with pytest.raises(ValueError, match="list"):
        load_grid(bad)


def test_empty_yaml_returns_empty_list(tmp_path: Path) -> None:
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    assert load_grid(empty) == []


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_grid(tmp_path / "nope.yaml")


def test_row_is_frozen_dataclass() -> None:
    rows = load_grid(MAIN_TABLE)
    row = rows[0]
    assert isinstance(row, GridRow)
    with pytest.raises(Exception):
        row.scenario_id = "mutated"  # type: ignore[misc]
