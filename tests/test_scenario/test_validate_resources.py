"""Validator checks for resource-aware scenario bundles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from clawsocialarena.generator.cli import _write_bundle
from clawsocialarena.generator.template import CategoryCode, TaskFamily, TemplateShape
from clawsocialarena.scenario.validate import validate_bundle


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _resource_shape(file_text: str) -> TemplateShape:
    return TemplateShape(
        scenario_id="resource-validator-v1",
        category=CategoryCode.CU,
        task_family=TaskFamily.SCHEDULING,
        agents=[
            {"agent_id": "alice", "user_id": "user-a", "system_prompt_template": "p"},
            {"agent_id": "bob", "user_id": "user-b", "system_prompt_template": "q"},
        ],
        initial_state={},
        max_turns=4,
        opening_message={"from": "alice", "to": "bob", "content": "start"},
        phase_schedule=[],
        declared_policies={"flat": [], "phase_scoped": []},
        terminal_predicate={"type": "resource_final_state"},
        invariants={},
        integrity_requirements={},
        planted_disclosures=[],
        resource_manifest={
            "resources": {
                "file-alice-notes": {
                    "resource_id": "file-alice-notes",
                    "type": "file",
                    "owner_id": "owner-alice",
                    "sensitivity": "confidential",
                    "path": "files/alice/private-notes.md",
                    "allowed_operations": [
                        {
                            "identity_id": "identity-alice-primary",
                            "scope_id": "scope-alice-files",
                            "operations": ["fs.read", "fs.write"],
                        }
                    ],
                    "initial_digest": _sha256_text(file_text),
                    "expected_final_digest": _sha256_text(file_text),
                }
            }
        },
        resource_fixtures={
            "files": {"files/alice/private-notes.md": file_text}
        },
    )


def test_validate_accepts_generated_resource_bundle(tmp_path: Path) -> None:
    shape = _resource_shape("Alice private note: passport P-123.\n")
    out_dir = tmp_path / shape.scenario_id

    _write_bundle(shape, out_dir)

    report = validate_bundle(out_dir)
    assert report.ok, f"unexpected errors: {report.errors}"


def test_validate_flags_resource_manifest_sidecar_mismatch(
    tmp_path: Path,
) -> None:
    shape = _resource_shape("Alice private note: passport P-123.\n")
    out_dir = tmp_path / shape.scenario_id
    _write_bundle(shape, out_dir)

    sidecar_path = out_dir / "resources" / "manifest.json"
    sidecar = json.loads(sidecar_path.read_text())
    sidecar["resources"]["file-alice-notes"]["sensitivity"] = "public"
    sidecar_path.write_text(json.dumps(sidecar, indent=2))

    report = validate_bundle(out_dir)
    assert not report.ok
    assert any("resources/manifest.json" in err for err in report.errors)


def test_validate_flags_resource_file_digest_mismatch(tmp_path: Path) -> None:
    shape = _resource_shape("Alice private note: passport P-123.\n")
    out_dir = tmp_path / shape.scenario_id
    _write_bundle(shape, out_dir)

    resource_file = out_dir / "resources/files/alice/private-notes.md"
    resource_file.write_text("tampered\n")

    report = validate_bundle(out_dir)
    assert not report.ok
    assert any("initial_digest" in err for err in report.errors)
