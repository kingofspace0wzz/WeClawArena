"""make_repro_bundle.py — tarball layout + replay.sh contents."""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from scripts.make_repro_bundle import build_bundle, main

from tests.test_analysis.fixtures import build_synthetic_scorecards


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Materialise a tiny stand-in repo that looks enough like v2-refactor."""

    root = tmp_path / "repo"
    root.mkdir()

    # Scenarios directory.
    scenarios = root / "benchmark" / "scenarios" / "v1.0.0"
    scenarios.mkdir(parents=True)
    (scenarios / "scenario-0.json").write_text('{"scenario_id": "s0"}')

    # Results tree uses the synthetic scorecard factory (24 scorecards).
    build_synthetic_scorecards(root / "results", version="v1.0.0")

    # pyproject + uv.lock stand-ins.
    (root / "pyproject.toml").write_text('[project]\nname = "fake"\nversion = "0.0.1"\n')
    (root / "uv.lock").write_text("# lockfile placeholder\n")

    # Preregistration.
    prereg = root / "docs" / "preregistration.md"
    prereg.parent.mkdir(parents=True)
    prereg.write_text("# Preregistration\n\n- H1, H2, H3, H4, H5\n")

    # Spec.
    spec = root / "docs" / "superpowers" / "specs" / "2026-04-17-clawsocialarena-v2-design.md"
    spec.parent.mkdir(parents=True)
    spec.write_text("# Spec\n")

    return root


def test_build_bundle_writes_a_tarball(tmp_path: Path, fake_repo: Path):
    out = tmp_path / "repro.tar.gz"
    path = build_bundle(version="1.0.0", out=out, repo_root=fake_repo)
    assert path == out
    assert out.exists()
    assert out.stat().st_size > 0


def test_tarball_contains_every_required_entry(tmp_path: Path, fake_repo: Path):
    out = tmp_path / "repro.tar.gz"
    build_bundle(version="1.0.0", out=out, repo_root=fake_repo)
    with tarfile.open(out, "r:gz") as tar:
        names = tar.getnames()
    required_suffixes = (
        "replay.sh",
        "pyproject.toml",
        "uv.lock",
        "docs/preregistration.md",
        "docs/superpowers/specs/2026-04-17-clawsocialarena-v2-design.md",
        "benchmark/scenarios/v1.0.0/scenario-0.json",
    )
    for suffix in required_suffixes:
        assert any(
            n.endswith(suffix) for n in names
        ), f"missing {suffix} (have: {names[:5]}...)"

    # Results tree is bundled (24 scorecards plus the ``v1.0.0`` parent).
    assert any(n.endswith("run_scorecard.json") for n in names)


def test_tarball_extracts_cleanly(tmp_path: Path, fake_repo: Path):
    out = tmp_path / "repro.tar.gz"
    build_bundle(version="1.0.0", out=out, repo_root=fake_repo)
    extract_dir = tmp_path / "extracted"
    extract_dir.mkdir()
    with tarfile.open(out, "r:gz") as tar:
        tar.extractall(extract_dir)
    # Single top-level dir named clawsocialarena-repro-v1.0.0.
    children = list(extract_dir.iterdir())
    assert len(children) == 1
    top = children[0]
    assert top.name == "clawsocialarena-repro-v1.0.0"
    replay = top / "replay.sh"
    assert replay.exists()
    # Executable bit preserved through tar.
    assert replay.stat().st_mode & 0o100


def test_replay_sh_runs_full_analysis_pipeline(tmp_path: Path, fake_repo: Path):
    out = tmp_path / "repro.tar.gz"
    build_bundle(version="1.0.0", out=out, repo_root=fake_repo)
    with tarfile.open(out, "r:gz") as tar:
        tar.extractall(tmp_path)
    replay = tmp_path / "clawsocialarena-repro-v1.0.0" / "replay.sh"
    script = replay.read_text()
    # Every stage of the analysis pipeline is wired.
    for fragment in (
        "python -m venv",
        "pip install",
        "clawsocialarena.analysis aggregate",
        "clawsocialarena.analysis table",
        "clawsocialarena.analysis figures",
        "clawsocialarena.analysis prereg",
    ):
        assert fragment in script


def test_bundle_emits_placeholders_when_inputs_missing(tmp_path: Path):
    fake = tmp_path / "bare"
    fake.mkdir()
    out = tmp_path / "repro.tar.gz"
    build_bundle(version="1.0.0", out=out, repo_root=fake)
    with tarfile.open(out, "r:gz") as tar:
        names = tar.getnames()
    # Placeholder notes stand in for missing scenarios, results, spec.
    assert any(n.endswith("PLACEHOLDER.md") for n in names)
    # Stub preregistration replaces the absent canonical doc.
    assert any(n.endswith("docs/preregistration.md") for n in names)


def test_cli_main_builds_the_bundle(tmp_path: Path, fake_repo: Path):
    out = tmp_path / "repro.tar.gz"
    rc = main(
        [
            "--version",
            "1.0.0",
            "--out",
            str(out),
            "--repo-root",
            str(fake_repo),
        ]
    )
    assert rc == 0
    assert out.exists()
