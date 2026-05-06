"""Resource manifest schema tests for Phase I.5."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from clawsocialarena.scenario.models import (
    GTBundle,
    ResourceManifest,
    ResourceType,
)


def _resource_manifest() -> dict:
    return {
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
                        "operations": ["fs.read", "fs.write"],
                    }
                ],
                "initial_digest": "sha256:initial-file",
                "expected_final_digest": "sha256:final-file",
            },
            "db-alice-health": {
                "resource_id": "db-alice-health",
                "type": "sqlite_db",
                "owner_id": "owner-alice",
                "sensitivity": "restricted",
                "path": "db/alice.sqlite",
                "table": "health_notes",
                "row_filter": {"user_id": "alice"},
                "allowed_operations": [
                    {
                        "identity_id": "identity-alice-primary",
                        "scope_id": "scope-alice-db",
                        "operations": ["db.query"],
                    }
                ],
                "initial_digest": "sha256:initial-db",
                "expected_final_digest": "sha256:final-db",
            },
        }
    }


def _gt_with_resources() -> dict:
    return {
        "scenario_id": "resource-v1",
        "canonical_action_stream": [],
        "phase_schedule": [],
        "policies": {"flat": [], "phase_scoped": []},
        "attribution_dag": {"nodes": [], "edges": []},
        "integrity_requirements": {},
        "terminal_predicate": {"type": "resource_final_state"},
        "invariants": {},
        "resource_manifest": _resource_manifest(),
    }


def test_resource_manifest_round_trips_file_and_database_entries() -> None:
    manifest = ResourceManifest.model_validate(_resource_manifest())

    file_entry = manifest.resources["file-alice-notes"]
    db_entry = manifest.resources["db-alice-health"]

    assert file_entry.resource_type == ResourceType.FILE
    assert file_entry.consent_required is True
    assert file_entry.allowed_operations[0].operations == ["fs.read", "fs.write"]
    assert db_entry.resource_type == ResourceType.SQLITE_DB
    assert db_entry.table == "health_notes"
    assert db_entry.row_filter == {"user_id": "alice"}
    assert json.loads(manifest.model_dump_json()) == _resource_manifest()


def test_resource_manifest_rejects_key_mismatch() -> None:
    manifest = _resource_manifest()
    manifest["resources"]["file-alice-notes"]["resource_id"] = "other-id"

    with pytest.raises(ValidationError):
        ResourceManifest.model_validate(manifest)


def test_resource_manifest_rejects_empty_allowed_operation_set() -> None:
    manifest = _resource_manifest()
    manifest["resources"]["file-alice-notes"]["allowed_operations"][0][
        "operations"
    ] = []

    with pytest.raises(ValidationError):
        ResourceManifest.model_validate(manifest)


def test_resource_manifest_rejects_unscoped_allowed_operation_set() -> None:
    manifest = _resource_manifest()
    rule = manifest["resources"]["file-alice-notes"]["allowed_operations"][0]
    del rule["identity_id"]
    del rule["scope_id"]

    with pytest.raises(ValidationError):
        ResourceManifest.model_validate(manifest)


def test_gt_bundle_carries_resource_manifest() -> None:
    gt = GTBundle.model_validate(_gt_with_resources())

    assert gt.resource_manifest is not None
    dumped = json.loads(gt.model_dump_json())
    assert dumped["resource_manifest"] == _resource_manifest()
    assert GTBundle.model_validate(dumped) == gt
