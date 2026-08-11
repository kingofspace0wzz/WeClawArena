from __future__ import annotations

from pathlib import Path

from scripts.validate_public_release import validate_public_release


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_public_release_contract() -> None:
    errors = validate_public_release(REPO_ROOT)

    assert errors == [], "\n".join(errors)
