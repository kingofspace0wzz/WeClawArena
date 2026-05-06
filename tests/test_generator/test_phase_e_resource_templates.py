"""Phase E templates with concrete personal resource fixtures."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clawsocialarena.generator.attack_injection import AttackType, inject_attack
from clawsocialarena.generator.cli import _write_bundle
from clawsocialarena.generator.gt_assembly import assemble_gt_bundle
from clawsocialarena.generator.templates.cu_scheduling import CUSchedulingTemplate
from clawsocialarena.scenario.models import GTBundle
from clawsocialarena.scenario.validate import validate_bundle


RESOURCE_ATTACKS = (
    AttackType.UNAUTHORIZED_FILE_DELETE,
    AttackType.SILENT_FILE_OVERWRITE,
    AttackType.CROSS_USER_FILE_READ,
    AttackType.SENSITIVE_DB_QUERY,
    AttackType.DB_TO_MESSAGE_EXFIL,
    AttackType.CONSENT_BYPASSED_UPDATE,
)


def test_cu_scheduling_declares_file_and_database_resources() -> None:
    shape = CUSchedulingTemplate().build(seed=7, scenario_id="cu-resource")

    resources = shape.resource_manifest["resources"]
    assert "file-bob-notes" in resources
    assert "db-bob-health" in resources
    assert resources["file-bob-notes"]["protected_content"]
    assert resources["db-bob-health"]["protected_content"]

    gt = assemble_gt_bundle(shape)
    assert {"fs.read", "fs.write", "fs.delete", "db.query", "db.update"} <= set(
        gt["mcp_tool_manifest"]
    )
    parsed = GTBundle.model_validate(gt)
    assert parsed.resource_manifest is not None


def test_cu_scheduling_resource_bundle_materializes_and_validates(
    tmp_path: Path,
) -> None:
    shape = CUSchedulingTemplate().build(seed=7, scenario_id="cu-resource")
    out_dir = tmp_path / shape.scenario_id

    _write_bundle(shape, out_dir)

    report = validate_bundle(out_dir)
    assert report.ok, report.errors
    assert (out_dir / "resources/files/bob/private-notes.md").exists()
    with sqlite3.connect(out_dir / "resources/db/bob.sqlite") as conn:
        row = conn.execute(
            "SELECT user_id, note FROM health_notes WHERE user_id = 'bob'"
        ).fetchone()
    assert row == ("bob", "allergy: shellfish")
    sidecar = json.loads((out_dir / "resources/manifest.json").read_text())
    assert sidecar == json.loads((out_dir / "scenario.gt.json").read_text())[
        "resource_manifest"
    ]


@pytest.mark.parametrize("attack_type", RESOURCE_ATTACKS)
def test_cu_scheduling_accepts_resource_attack_injection(
    tmp_path: Path,
    attack_type: AttackType,
) -> None:
    shape = CUSchedulingTemplate().build(seed=7, scenario_id=f"cu-{attack_type.value}")

    injected = inject_attack(
        shape=shape,
        attack_type=attack_type,
        attacker_agent_id="alice",
    )
    out_dir = tmp_path / injected.scenario_id
    _write_bundle(injected, out_dir)

    report = validate_bundle(out_dir)
    assert report.ok, report.errors
    gt = json.loads((out_dir / "scenario.gt.json").read_text())
    assert gt["attack_plan"]["axis"] == "resource"
    assert gt["attack_plan"]["target_resource_id"] in {
        "file-bob-notes",
        "db-bob-health",
    }
