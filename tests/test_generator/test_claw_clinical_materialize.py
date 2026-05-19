"""Tests for the claw_clinical materializer."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.generator.family_packs.claw_clinical.loader import (
    load_referral_scenario,
)
from clawsocialarena.generator.family_packs.claw_clinical.materialize import (
    materialize_clinical_bundle,
)


@pytest.fixture
def simple_bundle_dir(tmp_path: Path) -> Path:
    bundle = load_referral_scenario()
    return materialize_clinical_bundle(bundle, tmp_path / "simple")


@pytest.fixture
def multi_dept_bundle_dir(tmp_path: Path) -> Path:
    bundle = load_referral_scenario(
        case_key="multi_dept_handoff_005",
        scenario_id="claw_clinical_multi_dept_005",
    )
    return materialize_clinical_bundle(bundle, tmp_path / "multi_dept")


def test_writes_top_level_artifacts(simple_bundle_dir: Path) -> None:
    for name in (
        "scenario.json",
        "scenario.gt.json",
        "family_pack_context.json",
        "docker-compose.yml",
    ):
        assert (simple_bundle_dir / name).is_file()


def test_personas_dir_has_agent_files(simple_bundle_dir: Path) -> None:
    personas = simple_bundle_dir / "personas"
    assert personas.is_dir()
    system_files = list(personas.glob("*.system.md"))
    tools_files = list(personas.glob("*.tools.json"))
    assert len(system_files) == 5  # attending, specialist, pharmacist, nurse, insurance
    assert len(tools_files) == 5


def test_mcp_dir_has_tool_stubs(simple_bundle_dir: Path) -> None:
    mcp = simple_bundle_dir / "mcp"
    assert mcp.is_dir()
    stubs = list(mcp.glob("*.json"))
    assert len(stubs) >= 23  # Base clinical tools


def test_emr_sqlite_has_patient_data(simple_bundle_dir: Path) -> None:
    # Find the EMR sqlite under shared/emr/
    emr_dirs = list((simple_bundle_dir / "resources" / "shared" / "emr").iterdir())
    assert len(emr_dirs) >= 1
    patient_dir = emr_dirs[0]
    db_path = patient_dir / "emr.sqlite"
    assert db_path.is_file()
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"patients", "medications", "referrals"}.issubset(tables)
        patient_count = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
        assert patient_count == 1


def test_restricted_records_exist(simple_bundle_dir: Path) -> None:
    emr_dirs = list((simple_bundle_dir / "resources" / "shared" / "emr").iterdir())
    patient_dir = emr_dirs[0]
    restricted = patient_dir / "restricted"
    assert restricted.is_dir()
    for record_type in ("psychiatric", "substance", "reproductive"):
        path = restricted / f"{record_type}.json"
        assert path.is_file()
        data = json.loads(path.read_text())
        assert data["access_requires_consent"] is True


def test_insurance_coverage_rules(simple_bundle_dir: Path) -> None:
    insurance_dir = simple_bundle_dir / "resources" / "shared" / "insurance"
    assert insurance_dir.is_dir()
    plans = list(insurance_dir.iterdir())
    assert len(plans) >= 1
    rules = json.loads((plans[0] / "coverage_rules.json").read_text())
    assert rules["referral_preauth_required"] is True
    assert "psychiatric" in rules["excluded_from_record_access"]


def test_gt_json_has_topology_aware_invariants(simple_bundle_dir: Path) -> None:
    gt = json.loads((simple_bundle_dir / "scenario.gt.json").read_text())
    inv = gt["invariants"]
    assert "privacy_must_not_cross" in inv
    assert "security_must_not_happen" in inv
    assert "governance_must_not_happen" in inv


def test_gt_json_mcp_manifest_includes_dept_tools(
    simple_bundle_dir: Path,
) -> None:
    gt = json.loads((simple_bundle_dir / "scenario.gt.json").read_text())
    manifest = gt["mcp_tool_manifest"]
    assert "read_department_notes" in manifest
    assert "write_department_notes" in manifest
    assert len(manifest) == 25


def test_multi_dept_writes_department_notes(multi_dept_bundle_dir: Path) -> None:
    dept_notes = multi_dept_bundle_dir / "resources" / "shared" / "dept_notes"
    assert dept_notes.is_dir()
    departments = list(dept_notes.iterdir())
    assert len(departments) == 3  # cardiology, nephrology, neurology


def test_multi_dept_sqlite_has_department_notes_table(
    multi_dept_bundle_dir: Path,
) -> None:
    emr_dirs = list((multi_dept_bundle_dir / "resources" / "shared" / "emr").iterdir())
    patient_dir = emr_dirs[0]
    db_path = patient_dir / "emr.sqlite"
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "department_notes" in tables


def test_resources_initial_is_mirror_copy(simple_bundle_dir: Path) -> None:
    resources = simple_bundle_dir / "resources"
    resources_initial = simple_bundle_dir / "resources_initial"
    assert resources_initial.is_dir()
    # Check that the shared EMR subtree exists in the mirror
    emr_dirs = list((resources_initial / "shared" / "emr").iterdir())
    assert len(emr_dirs) >= 1


def test_agent_private_resources_use_owner_id(simple_bundle_dir: Path) -> None:
    agents_dir = simple_bundle_dir / "resources" / "agents"
    assert agents_dir.is_dir()
    # At least one agent owner directory should exist
    owner_dirs = list(agents_dir.iterdir())
    assert len(owner_dirs) >= 1
    # Each should have a files/ subdirectory with memory_bank.json
    for od in owner_dirs:
        files_dir = od / "files"
        assert files_dir.is_dir()
        assert (files_dir / "memory_bank.json").is_file()
        assert (files_dir / "personal_info.json").is_file()


def test_multi_dept_gt_has_cross_department_privacy(
    multi_dept_bundle_dir: Path,
) -> None:
    gt = json.loads((multi_dept_bundle_dir / "scenario.gt.json").read_text())
    inv = gt["invariants"]
    privacy = inv["privacy_must_not_cross"]
    # Should have cross-department notes privacy
    sources = [p.get("source_scope", "") for p in privacy]
    assert any("dept_notes" in s for s in sources)
