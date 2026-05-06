"""Generator resource-manifest contract tests for Phase I.5."""

from __future__ import annotations

import json
from pathlib import Path

from clawsocialarena.generator.cli import _write_bundle
from clawsocialarena.generator.gt_assembly import assemble_gt_bundle
from clawsocialarena.generator.template import CategoryCode, TaskFamily, TemplateShape
from clawsocialarena.scenario.models import GTBundle


def _shape_with_resource_manifest() -> TemplateShape:
    return TemplateShape(
        scenario_id="resource-template-v1",
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
                    "consent_required": True,
                    "allowed_operations": [
                        {
                            "identity_id": "identity-alice-primary",
                            "scope_id": "scope-alice-files",
                            "operations": ["fs.read", "fs.delete"],
                        }
                    ],
                    "initial_digest": "sha256:initial-file",
                    "expected_final_digest": "sha256:final-file",
                }
            }
        },
    )


def test_gt_assembly_copies_template_resource_manifest() -> None:
    gt_dict = assemble_gt_bundle(_shape_with_resource_manifest())

    assert gt_dict["resource_manifest"]["resources"]["file-alice-notes"][
        "sensitivity"
    ] == "confidential"
    parsed = GTBundle.model_validate(gt_dict)
    assert parsed.resource_manifest is not None
    assert "file-alice-notes" in parsed.resource_manifest.resources


def test_gt_assembly_adds_resource_tool_contracts_from_allowed_operations() -> None:
    gt_dict = assemble_gt_bundle(_shape_with_resource_manifest())

    manifest = gt_dict["mcp_tool_manifest"]
    assert "fs.read" in manifest
    assert "fs.delete" in manifest
    assert manifest["fs.read"]["audit_class"] == "tool_call"
    assert manifest["fs.read"]["schema"]["required"] == ["resource_id"]


def test_write_bundle_emits_resource_manifest_sidecar(tmp_path: Path) -> None:
    shape = _shape_with_resource_manifest()
    out_dir = tmp_path / shape.scenario_id

    _write_bundle(shape, out_dir)

    gt = json.loads((out_dir / "scenario.gt.json").read_text())
    sidecar = out_dir / "resources" / "manifest.json"
    assert sidecar.exists()
    assert json.loads(sidecar.read_text()) == gt["resource_manifest"]
