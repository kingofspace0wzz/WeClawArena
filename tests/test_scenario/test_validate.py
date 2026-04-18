"""Scenario validator v2 tests (Task D9).

The validator is exercised against two classes of bundles:

- ``tests/test_scenario/fixtures/v2_valid/`` -- bundles materialised on
  disk via the generator CLI at test start. They serve as both fixtures
  and a correctness-harness for the CLI's own bundle emission.
- ``tests/test_scenario/fixtures/v2_invalid/`` -- deliberately broken
  copies of the valid bundle. Each test targets one class of failure
  (bad YAML, missing persona file, MCP manifest inconsistency, broken GT
  bundle) and asserts the validator flags it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from clawsocialarena.generator.cli import main as cli_main
from clawsocialarena.scenario.validate import (
    ValidationReport,
    validate_bundle,
)


FIXTURES_ROOT = Path(__file__).parent / "fixtures"


def _build_valid_bundle(tmp_path: Path, *, seed: int = 501) -> Path:
    """Generate one CU-scheduling bundle via the CLI and return its path."""
    out_root = tmp_path / "gen"
    rc = cli_main([
        "--category", "CU", "--family", "scheduling",
        "--n", "1", "--seed", str(seed),
        "--out", str(out_root),
    ])
    assert rc == 0
    return next(out_root.iterdir())


def _copy_fixture(src: Path, dst: Path) -> Path:
    shutil.copytree(src, dst)
    return dst


def test_validate_bundle_passes_on_generated_v2_bundle(tmp_path: Path):
    bundle = _build_valid_bundle(tmp_path)
    report = validate_bundle(bundle)
    assert isinstance(report, ValidationReport)
    assert report.ok, f"expected valid; got errors: {report.errors}"


def test_validate_bundle_flags_missing_compose_yaml(tmp_path: Path):
    bundle = _build_valid_bundle(tmp_path)
    (bundle / "docker-compose.yml").unlink()
    report = validate_bundle(bundle)
    assert not report.ok
    assert any("docker-compose.yml" in e for e in report.errors)


def test_validate_bundle_flags_unparseable_compose_yaml(tmp_path: Path):
    bundle = _build_valid_bundle(tmp_path)
    (bundle / "docker-compose.yml").write_text("::: not : valid\n: yaml ::\n")
    report = validate_bundle(bundle)
    assert not report.ok
    assert any("docker-compose.yml" in e for e in report.errors)


def test_validate_bundle_flags_missing_persona_file(tmp_path: Path):
    bundle = _build_valid_bundle(tmp_path)
    (bundle / "personas" / "alice.system.md").unlink()
    report = validate_bundle(bundle)
    assert not report.ok
    assert any("alice.system.md" in e for e in report.errors)


def test_validate_bundle_flags_missing_mcp_config(tmp_path: Path):
    bundle = _build_valid_bundle(tmp_path)
    # Inject a tool into gt.mcp_tool_manifest without writing the mcp config.
    gt_path = bundle / "scenario.gt.json"
    gt_data = json.loads(gt_path.read_text())
    gt_data["mcp_tool_manifest"] = {
        "calendar": {
            "schema": {"type": "object"},
            "audit_class": "outbound_message",
        },
    }
    gt_path.write_text(json.dumps(gt_data, indent=2))
    report = validate_bundle(bundle)
    assert not report.ok
    assert any("calendar" in e for e in report.errors)


def test_validate_bundle_flags_mismatched_mcp_url(tmp_path: Path):
    bundle = _build_valid_bundle(tmp_path)
    gt_path = bundle / "scenario.gt.json"
    gt_data = json.loads(gt_path.read_text())
    gt_data["mcp_tool_manifest"] = {
        "calendar": {
            "schema": {"type": "object"},
            "audit_class": "outbound_message",
        },
    }
    gt_path.write_text(json.dumps(gt_data, indent=2))

    mcp_dir = bundle / "mcp"
    mcp_dir.mkdir(parents=True, exist_ok=True)
    (mcp_dir / "calendar.json").write_text(
        json.dumps({
            "tool_name": "calendar",
            "type": "http",
            "url": "http://gateway:8080/mcp/WRONG_TOOL_NAME",
        })
    )

    report = validate_bundle(bundle)
    assert not report.ok
    assert any("url" in e for e in report.errors)


def test_validate_bundle_flags_invalid_gt_schema(tmp_path: Path):
    bundle = _build_valid_bundle(tmp_path)
    # Drop the required terminal_predicate field to break GTBundle validation.
    gt_path = bundle / "scenario.gt.json"
    gt_data = json.loads(gt_path.read_text())
    gt_data.pop("terminal_predicate")
    gt_path.write_text(json.dumps(gt_data))
    report = validate_bundle(bundle)
    assert not report.ok
    assert any("scenario.gt.json" in e for e in report.errors)


def test_validate_bundle_missing_directory_is_error(tmp_path: Path):
    report = validate_bundle(tmp_path / "does_not_exist")
    assert not report.ok
    assert any("not a directory" in e for e in report.errors)


def test_validate_bundle_empty_mcp_manifest_does_not_require_mcp_dir(
    tmp_path: Path,
):
    """When the GT bundle declares no tools, the mcp/ dir can be empty."""
    bundle = _build_valid_bundle(tmp_path)
    # CU scheduling template declares no tools, so manifest is empty.
    # Dropping the mcp/ dir entirely should still validate.
    shutil.rmtree(bundle / "mcp")
    report = validate_bundle(bundle)
    assert report.ok, f"unexpected errors: {report.errors}"


def test_validate_main_cli_returns_zero_on_valid_bundle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    bundle = _build_valid_bundle(tmp_path)
    from clawsocialarena.scenario.validate import main as validate_main
    rc = validate_main([str(bundle)])
    assert rc == 0
    assert "ok" in capsys.readouterr().out


def test_validate_main_cli_returns_nonzero_on_invalid_bundle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    bundle = _build_valid_bundle(tmp_path)
    (bundle / "scenario.json").unlink()
    from clawsocialarena.scenario.validate import main as validate_main
    rc = validate_main([str(bundle)])
    assert rc == 1


def test_validate_static_v2_valid_fixture_passes():
    fixture = FIXTURES_ROOT / "v2_valid" / "cu_scheduling_valid"
    report = validate_bundle(fixture)
    assert report.ok, f"expected valid; got errors: {report.errors}"


def test_validate_static_v2_invalid_fixture_fails():
    fixture = FIXTURES_ROOT / "v2_invalid" / "cu_scheduling_no_compose"
    report = validate_bundle(fixture)
    assert not report.ok
