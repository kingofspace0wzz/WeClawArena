from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawsocialarena.generator.family_packs.swebench_workspace import (
    load_workspace_coding_v2_scenario,
)
from scripts.materialize_swebench_workspace_v2_calibration import (
    materialize_calibration_store,
)


def test_load_workspace_coding_v2_scenario_returns_v2_bundle() -> None:
    bundle = load_workspace_coding_v2_scenario()

    assert bundle.metadata["workspace_substrate_version"] == "v2"
    assert bundle.scenario.initial_state["workspace_substrate_version"] == "v2"


def test_materialize_v2_calibration_store_records_manifest_rows(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "calibration"

    manifest = materialize_calibration_store(out_dir=out_dir, limit=2)

    assert manifest["n_bases"] == 2
    assert manifest["n_modes"] == 5
    assert manifest["n_variants"] == 10
    assert manifest["workspace_substrate_version"] == "v2"
    stored = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert stored == manifest
    assert {row["attack_mode"] for row in stored["rows"]} == {
        "no_attacker",
        "security",
        "privacy",
        "governance",
        "collaboration",
    }
    assert {row["family_id"] for row in stored["rows"]} == {"swebench_workspace"}
    assert all(
        row["bundle_dir"].startswith("swebench_workspace/")
        for row in stored["rows"]
    )
    assert [row["variant_id"] for row in stored["rows"]] == sorted(
        row["variant_id"] for row in stored["rows"]
    )


def test_materialize_v2_calibration_store_writes_v2_bundle_metadata(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "calibration"

    manifest = materialize_calibration_store(out_dir=out_dir, limit=1)

    bundle_dir = out_dir / manifest["rows"][0]["bundle_dir"]
    metadata = json.loads(
        (bundle_dir / "phase5_metadata.json").read_text(encoding="utf-8")
    )
    context = json.loads(
        (bundle_dir / "family_pack_context.json").read_text(encoding="utf-8")
    )

    assert metadata["workspace_substrate_version"] == "v2"
    assert (
        metadata["task_variant"]["loader_kwargs"]["workspace_substrate_version"]
        == "v2"
    )
    assert context["workspace_substrate_version"] == "v2"


def test_materialize_v2_calibration_store_rejects_invalid_limit(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "calibration"

    with pytest.raises(ValueError, match="limit must be positive"):
        materialize_calibration_store(out_dir=out_dir, limit=-1)

    assert not out_dir.exists()


def test_materialize_v2_calibration_store_force_refuses_unmarked_dir(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "calibration"
    out_dir.mkdir()
    sentinel = out_dir / "manual-notes.txt"
    sentinel.write_text("do not delete", encoding="utf-8")

    with pytest.raises(FileExistsError, match="not a swebench_workspace v2 calibration"):
        materialize_calibration_store(out_dir=out_dir, limit=1, force=True)

    assert sentinel.read_text(encoding="utf-8") == "do not delete"


@pytest.mark.parametrize(
    "manifest",
    [
        {
            "workspace_substrate_version": "v2",
            "naturalization_model": "none",
            "n_modes": 5,
            "n_variants": 0,
            "rows": [],
        },
        {
            "workspace_substrate_version": "v2",
            "naturalization_model": "none",
            "n_modes": 5,
            "n_variants": 1,
            "rows": [{"bundle_dir": "swebench_workspace/base"}],
        },
    ],
)
def test_materialize_v2_calibration_store_force_refuses_weak_manifest(
    tmp_path: Path,
    manifest: dict[str, object],
) -> None:
    out_dir = tmp_path / "calibration"
    out_dir.mkdir()
    sentinel = out_dir / "manual-notes.txt"
    sentinel.write_text("do not delete", encoding="utf-8")
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )

    with pytest.raises(FileExistsError, match="not a swebench_workspace v2 calibration"):
        materialize_calibration_store(out_dir=out_dir, limit=1, force=True)

    assert sentinel.read_text(encoding="utf-8") == "do not delete"


def test_materialize_v2_calibration_store_force_replaces_prior_store(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "calibration"
    first = materialize_calibration_store(out_dir=out_dir, limit=1)
    stale_bundle = out_dir / first["rows"][0]["bundle_dir"]
    assert stale_bundle.is_dir()

    second = materialize_calibration_store(out_dir=out_dir, limit=2, force=True)

    assert second["n_bases"] == 2
    assert second["n_variants"] == 10
