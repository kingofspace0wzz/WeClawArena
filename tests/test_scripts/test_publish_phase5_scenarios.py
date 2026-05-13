"""Unit tests for scripts/publish_phase5_scenarios.py."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


def _make_fake_scaffold(tmp_path: Path, n_bases: int = 2) -> Path:
    """Stand up a minimal pre-naturalization scaffold with N bases."""
    root = tmp_path / "scaffold"
    for i in range(n_bases):
        base = root / f"CELL-{i}" / "task0"
        base.mkdir(parents=True)
        (base / "scenario.json").write_text(json.dumps({
            "scenario_id": f"CELL-{i}__t0",
            "agents": [{"agent_id": "a1"}],
            "family_id": "tau2_telecom",
        }))
        (base / "scenario.gt.json").write_text(json.dumps({
            "construction_manifest": {"family_id": "tau2_telecom"},
        }))
        (base / "family_pack_context.json").write_text("{}")
        (base / "phase5_metadata.json").write_text(json.dumps({
            "base_scenario_id": f"CELL-{i}__t0",
            "cell": f"CELL-{i}",
            "task_variant": "v0",
            "phase5_version": 2,
        }))
    return root


class _FakeNaturalizationClient:
    """Returns a deterministic patch; counts calls for cache assertions."""

    def __init__(self) -> None:
        self.calls = 0

    def naturalize(self, *, base_dir: Path) -> dict[str, Any]:
        self.calls += 1
        return {
            "naturalization_status": "ok",
            "personas": {"a1": {"system_md": "You are a1.", "tools_json": {}}},
            "rendered_scenario_overrides": {},
            "tokens_used": {"prompt": 1000, "completion": 200},
        }


def test_publish_hash_function_is_deterministic(tmp_path: Path) -> None:
    """input_hash is the same when the input bytes are the same."""
    from scripts.publish_phase5_scenarios import compute_input_hash

    scaffold = _make_fake_scaffold(tmp_path)
    base = scaffold / "CELL-0" / "task0"
    h1 = compute_input_hash(base)
    h2 = compute_input_hash(base)
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_publish_skips_when_input_hash_matches(tmp_path: Path) -> None:
    """Second run with unchanged input does zero naturalization calls."""
    from scripts.publish_phase5_scenarios import publish_all

    scaffold = _make_fake_scaffold(tmp_path)
    store = tmp_path / "store"
    client = _FakeNaturalizationClient()

    publish_all(scaffold_dir=scaffold, store_dir=store, client=client,
                naturalization_model="test-model")
    assert client.calls == 2

    publish_all(scaffold_dir=scaffold, store_dir=store, client=client,
                naturalization_model="test-model")
    assert client.calls == 2, "cache should have prevented additional calls"


def test_publish_force_flag_bypasses_cache(tmp_path: Path) -> None:
    """--force re-runs naturalization regardless of cache."""
    from scripts.publish_phase5_scenarios import publish_all

    scaffold = _make_fake_scaffold(tmp_path)
    store = tmp_path / "store"
    client = _FakeNaturalizationClient()

    publish_all(scaffold_dir=scaffold, store_dir=store, client=client,
                naturalization_model="test-model")
    publish_all(scaffold_dir=scaffold, store_dir=store, client=client,
                naturalization_model="test-model", force=True)
    assert client.calls == 4


def test_publish_emits_manifest_with_expected_rows(tmp_path: Path) -> None:
    """After publish, manifest.json has N_bases x 5 rows sorted by variant_id."""
    from scripts.publish_phase5_scenarios import publish_all

    scaffold = _make_fake_scaffold(tmp_path, n_bases=2)
    store = tmp_path / "store"
    client = _FakeNaturalizationClient()

    publish_all(scaffold_dir=scaffold, store_dir=store, client=client,
                naturalization_model="test-model")

    manifest = json.loads((store / "manifest.json").read_text())
    assert manifest["n_bases"] == 2
    assert manifest["n_modes"] == 5
    assert manifest["n_variants"] == 10
    variant_ids = [r["variant_id"] for r in manifest["rows"]]
    assert variant_ids == sorted(variant_ids)
    modes = {r["attack_mode"] for r in manifest["rows"]}
    assert modes == {"no_attacker", "collaboration", "security",
                      "privacy", "governance"}
