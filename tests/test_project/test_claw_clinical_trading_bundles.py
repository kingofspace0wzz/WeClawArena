from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from clawsocialarena.scenario.validate import validate_bundle


REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_ROOT = REPO_ROOT / "benchmark/scenarios/v2.0.0"
MANIFEST_PATH = SCENARIO_ROOT / "manifest.json"
FAMILIES = {"claw_clinical": 10, "claw_trading": 8}
ATTACK_MODES = {"collaboration", "governance", "no_attacker", "privacy", "security"}
REQUIRED_FILES = {
    "scenario.json",
    "scenario.gt.json",
    "family_pack_context.json",
    "phase5_metadata.json",
    "naturalization_record.json",
    "docker-compose.yml",
    "personas",
    "mcp",
    "resources",
    "governance",
}


def _manifest_rows() -> list[dict]:
    return json.loads(MANIFEST_PATH.read_text())["rows"]


def test_claw_clinical_trading_manifest_rows_point_to_bundles() -> None:
    rows = [
        row
        for row in _manifest_rows()
        if row["family_id"] in {"claw_clinical", "claw_trading"}
    ]

    assert len(rows) == 90
    assert Counter(row["family_id"] for row in rows) == {
        "claw_clinical": 50,
        "claw_trading": 40,
    }
    assert Counter(row["base_id"] for row in rows).most_common(1)[0][1] == 5

    for family_id, base_count in FAMILIES.items():
        bases = {row["base_id"] for row in rows if row["family_id"] == family_id}
        assert len(bases) == base_count
        for base_id in bases:
            mode_set = {
                row["attack_mode"]
                for row in rows
                if row["family_id"] == family_id and row["base_id"] == base_id
            }
            assert mode_set == ATTACK_MODES

    for row in rows:
        assert (SCENARIO_ROOT / row["bundle_dir"]).is_dir()


def test_claw_clinical_trading_bundles_validate() -> None:
    rows = _manifest_rows()
    bundle_dirs = sorted(
        {
            SCENARIO_ROOT / row["bundle_dir"]
            for row in rows
            if row["family_id"] in {"claw_clinical", "claw_trading"}
        }
    )

    assert len(bundle_dirs) == 18
    for bundle_dir in bundle_dirs:
        for required in REQUIRED_FILES:
            assert (bundle_dir / required).exists(), f"{bundle_dir} missing {required}"
        report = validate_bundle(bundle_dir)
        assert report.ok, "\n".join(report.errors)
