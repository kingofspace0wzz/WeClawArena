"""Scenario validator v2 tests (Task D9 + Phase D.5 runtime contract).

The validator is exercised against two classes of bundles:

- ``tests/test_scenario/fixtures/v2_valid/`` -- bundles materialised on
  disk via the generator CLI at test start. They serve as both fixtures
  and a correctness-harness for the CLI's own bundle emission.
- ``tests/test_scenario/fixtures/v2_invalid/`` -- deliberately broken
  copies of the valid bundle. Each test targets one class of failure
  (bad YAML, missing persona file, MCP manifest inconsistency, broken GT
  bundle) and asserts the validator flags it.

Phase D.5 adds six runtime-contract checks on top of the D9 skeleton.
Tests below exercise each one in isolation.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

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


# --- Phase D.5 runtime-contract tests ----------------------------------------


def _rewrite_compose(bundle: Path, mutate) -> None:
    """Read the bundle's compose yaml, apply ``mutate(doc)``, write back."""
    path = bundle / "docker-compose.yml"
    doc = yaml.safe_load(path.read_text())
    mutate(doc)
    path.write_text(yaml.safe_dump(doc, sort_keys=False))


def test_validate_flags_missing_gateway_service(tmp_path: Path):
    """Fix 3.1: compose must declare a `gateway` service."""
    bundle = _build_valid_bundle(tmp_path)

    def _drop_gateway(doc):
        doc["services"].pop("gateway", None)

    _rewrite_compose(bundle, _drop_gateway)
    report = validate_bundle(bundle)
    assert not report.ok
    assert any("'gateway'" in e for e in report.errors)


def test_validate_flags_missing_agent_service(tmp_path: Path):
    """Fix 3.1: every scenario agent needs a matching service."""
    bundle = _build_valid_bundle(tmp_path)

    def _drop_alice(doc):
        doc["services"].pop("alice", None)

    _rewrite_compose(bundle, _drop_alice)
    report = validate_bundle(bundle)
    assert not report.ok
    assert any("alice" in e for e in report.errors)


def test_validate_flags_unexpected_extra_service(tmp_path: Path):
    """Fix 3.1: unknown extras in the services map are flagged."""
    bundle = _build_valid_bundle(tmp_path)

    def _add_phantom(doc):
        doc["services"]["phantom"] = {"image": "nginx:alpine"}

    _rewrite_compose(bundle, _add_phantom)
    report = validate_bundle(bundle)
    assert not report.ok
    assert any("phantom" in e for e in report.errors)


def test_validate_flags_missing_gateway_url_env_var(tmp_path: Path):
    """Fix 3.2: CLAWSOCIAL_GATEWAY_URL must be present per agent."""
    bundle = _build_valid_bundle(tmp_path)

    def _strip_url(doc):
        env = doc["services"]["alice"]["environment"]
        doc["services"]["alice"]["environment"] = [
            e for e in env if not e.startswith("CLAWSOCIAL_GATEWAY_URL")
        ]

    _rewrite_compose(bundle, _strip_url)
    report = validate_bundle(bundle)
    assert not report.ok
    assert any("CLAWSOCIAL_GATEWAY_URL" in e for e in report.errors)


def test_validate_flags_wrong_agent_id_env_var(tmp_path: Path):
    """Fix 3.2: CLAWSOCIAL_AGENT_ID must match the service name."""
    bundle = _build_valid_bundle(tmp_path)

    def _twist_id(doc):
        env = doc["services"]["alice"]["environment"]
        doc["services"]["alice"]["environment"] = [
            "CLAWSOCIAL_AGENT_ID=not-alice" if e.startswith("CLAWSOCIAL_AGENT_ID") else e
            for e in env
        ]

    _rewrite_compose(bundle, _twist_id)
    report = validate_bundle(bundle)
    assert not report.ok
    assert any("CLAWSOCIAL_AGENT_ID" in e for e in report.errors)


def test_validate_flags_persona_manifest_missing_agent(tmp_path: Path):
    """Fix 3.3: persona_manifest must list every agent."""
    bundle = _build_valid_bundle(tmp_path)
    gt_path = bundle / "scenario.gt.json"
    gt_data = json.loads(gt_path.read_text())
    gt_data["persona_manifest"].pop("alice", None)
    gt_path.write_text(json.dumps(gt_data, indent=2))

    report = validate_bundle(bundle)
    assert not report.ok
    assert any(
        "persona_manifest" in e and "alice" in e for e in report.errors
    )


def test_validate_flags_persona_manifest_orphan_entry(tmp_path: Path):
    """Fix 3.3: persona_manifest entries not in scenario.agents are errors."""
    bundle = _build_valid_bundle(tmp_path)
    gt_path = bundle / "scenario.gt.json"
    gt_data = json.loads(gt_path.read_text())
    gt_data["persona_manifest"]["ghost"] = {
        "profile_ref": "asb://profiles/ghost",
        "agent_id": "ghost",
    }
    gt_path.write_text(json.dumps(gt_data, indent=2))

    report = validate_bundle(bundle)
    assert not report.ok
    assert any("ghost" in e for e in report.errors)


def test_validate_flags_persona_manifest_mismatched_inner_id(tmp_path: Path):
    """Fix 3.3: inner agent_id must equal the manifest key."""
    bundle = _build_valid_bundle(tmp_path)
    gt_path = bundle / "scenario.gt.json"
    gt_data = json.loads(gt_path.read_text())
    gt_data["persona_manifest"]["alice"]["agent_id"] = "bob"
    gt_path.write_text(json.dumps(gt_data, indent=2))

    report = validate_bundle(bundle)
    assert not report.ok
    assert any("persona_manifest" in e for e in report.errors)


def test_validate_flags_persona_tools_referring_undeclared_tool(tmp_path: Path):
    """Fix 3.4: .tools.json only lists tools in gt.mcp_tool_manifest."""
    bundle = _build_valid_bundle(tmp_path)
    # CU-scheduling declares no tools, so any tool name is undeclared.
    tools_path = bundle / "personas" / "alice.tools.json"
    tools_path.write_text(json.dumps(["calendar"]))

    report = validate_bundle(bundle)
    assert not report.ok
    assert any(
        "calendar" in e and "mcp_tool_manifest" in e for e in report.errors
    )


def test_validate_flags_unresolvable_relative_build_context(tmp_path: Path):
    """Fix 3.5: relative build.context that does not resolve is flagged."""
    bundle = _build_valid_bundle(tmp_path)

    def _break_ctx(doc):
        doc["services"]["alice"]["build"]["context"] = "../../nope-does-not-exist"

    _rewrite_compose(bundle, _break_ctx)
    report = validate_bundle(bundle)
    assert not report.ok
    assert any("build.context" in e for e in report.errors)


def test_validate_accepts_dot_build_context(tmp_path: Path):
    """Fix 3.5: `.` is explicitly allowed as a build.context."""
    bundle = _build_valid_bundle(tmp_path)

    def _make_dot(doc):
        for svc in doc["services"].values():
            if "build" in svc:
                svc["build"]["context"] = "."

    _rewrite_compose(bundle, _make_dot)
    report = validate_bundle(bundle)
    assert report.ok, f"unexpected errors: {report.errors}"


def test_validate_flags_missing_persona_volume_mount(tmp_path: Path):
    """Fix 3.6: agent service must mount its own persona + tools + mcp dir."""
    bundle = _build_valid_bundle(tmp_path)

    def _drop_persona_mount(doc):
        vols = doc["services"]["alice"]["volumes"]
        doc["services"]["alice"]["volumes"] = [
            v for v in vols if "persona.system.md" not in v
        ]

    _rewrite_compose(bundle, _drop_persona_mount)
    report = validate_bundle(bundle)
    assert not report.ok
    assert any(
        "persona.system.md" in e for e in report.errors
    )


def test_validate_flags_missing_mcp_volume_mount(tmp_path: Path):
    """Fix 3.6: agent service must mount the shared mcp/ directory."""
    bundle = _build_valid_bundle(tmp_path)

    def _drop_mcp_mount(doc):
        vols = doc["services"]["alice"]["volumes"]
        doc["services"]["alice"]["volumes"] = [
            v for v in vols if ":/workspace/mcp:" not in v
        ]

    _rewrite_compose(bundle, _drop_mcp_mount)
    report = validate_bundle(bundle)
    assert not report.ok
    assert any("/workspace/mcp" in e for e in report.errors)
