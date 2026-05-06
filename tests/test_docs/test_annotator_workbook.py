"""Annotator workbook contract tests."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKBOOK = REPO_ROOT / "docs" / "annotator_workbook_template.md"


def test_annotator_workbook_includes_resource_fields() -> None:
    content = WORKBOOK.read_text(encoding="utf-8")

    for field in (
        "resource_id",
        "resource_type",
        "resource_owner_id",
        "allowed_operations",
        "consent_required",
        "expected_final_digest",
        "protected_content",
    ):
        assert field in content
