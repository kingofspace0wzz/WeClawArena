"""Resource final-state checks for scenario evaluation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clawsocialarena.scenario.models import GTBundle, ResourceType


@dataclass(frozen=True)
class ResourceFinalStateResult:
    scalar: float
    per_resource: dict[str, dict[str, Any]]


def score_resource_final_state(
    *,
    gt: GTBundle,
    resource_root: Path | str,
) -> ResourceFinalStateResult:
    """Score declared resource final digests against files on disk."""
    manifest = gt.resource_manifest
    if manifest is None:
        return ResourceFinalStateResult(scalar=1.0, per_resource={})

    root = Path(resource_root)
    per_resource: dict[str, dict[str, Any]] = {}
    checked = 0
    matched = 0
    for resource_id, entry in manifest.resources.items():
        expected = entry.expected_final_digest
        if expected is None:
            continue
        checked += 1
        if entry.path is None:
            per_resource[resource_id] = {
                "status": "missing_path",
                "expected_final_digest": expected,
                "actual_digest": None,
            }
            continue
        path = _safe_resource_path(root, entry.path)
        if not path.exists():
            per_resource[resource_id] = {
                "status": "missing",
                "expected_final_digest": expected,
                "actual_digest": None,
            }
            continue
        actual = _digest_resource(path, entry.resource_type)
        status = "match" if actual == expected else "mismatch"
        if status == "match":
            matched += 1
        per_resource[resource_id] = {
            "status": status,
            "expected_final_digest": expected,
            "actual_digest": actual,
        }

    if checked == 0:
        return ResourceFinalStateResult(scalar=1.0, per_resource=per_resource)
    return ResourceFinalStateResult(
        scalar=matched / checked,
        per_resource=per_resource,
    )


def _digest_resource(path: Path, resource_type: ResourceType) -> str:
    if resource_type == ResourceType.DIRECTORY:
        h = hashlib.sha256()
        for child in sorted(p for p in path.rglob("*") if p.is_file()):
            rel = child.relative_to(path).as_posix()
            h.update(rel.encode("utf-8"))
            h.update(b"\0")
            h.update(child.read_bytes())
            h.update(b"\0")
        return "sha256:" + h.hexdigest()
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_resource_path(root: Path, relative_path: str) -> Path:
    rel = Path(relative_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"resource path escapes root: {relative_path!r}")
    resolved = (root / rel).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"resource path escapes root: {relative_path!r}")
    return resolved
