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


def test_naturalization_preserves_runtime_identity_contract_and_tools(
    tmp_path: Path,
) -> None:
    from scripts.publish_phase5_scenarios import _apply_naturalization_patch

    store_base = tmp_path / "store" / "bargaining" / "CASE__t0"
    personas = store_base / "personas"
    personas.mkdir(parents=True)
    (personas / "buyer.system.md").write_text(
        "# buyer\n\n"
        "## Runtime Interface\n\n"
        "- Agent ID: `buyer`\n"
        "- Owner ID: `buyer_owner`\n\n"
        "## Persona prompt\n\n"
        "Old deterministic prompt.\n",
        encoding="utf-8",
    )
    (personas / "buyer.tools.json").write_text(
        json.dumps(["read_owned_file", "request_purchase_approval"]),
        encoding="utf-8",
    )

    _apply_naturalization_patch(
        store_base=store_base,
        patch={
            "personas": {
                "buyer": {
                    "system_md": "Naturalized buyer prose.",
                    "tools_json": {},
                }
            }
        },
    )

    system_md = (personas / "buyer.system.md").read_text(encoding="utf-8")
    tools = json.loads((personas / "buyer.tools.json").read_text(encoding="utf-8"))
    assert "## Runtime Interface" in system_md
    assert "Agent ID: `buyer`" in system_md
    assert "Owner ID: `buyer_owner`" in system_md
    assert "Naturalized buyer prose." in system_md
    assert "Old deterministic prompt." not in system_md
    assert tools == ["read_owned_file", "request_purchase_approval"]


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
    assert sorted(
        p.relative_to(store).as_posix() for p in store.glob("telecom/CELL-*__t0")
    ) == [
        "telecom/CELL-0__t0",
        "telecom/CELL-1__t0",
    ]
    variant_ids = [r["variant_id"] for r in manifest["rows"]]
    assert variant_ids == sorted(variant_ids)
    modes = {r["attack_mode"] for r in manifest["rows"]}
    assert modes == {"no_attacker", "collaboration", "security",
                      "privacy", "governance"}
    for row in manifest["rows"]:
        assert row["family_id"] == "tau2_telecom"
        assert row["cell_id"] in {"CELL-0", "CELL-1"}
        assert row["task_index"] == 0
        assert row["bundle_dir"] == f"telecom/{row['base_id']}"


def test_publish_manifest_uses_nested_phase5_metadata(tmp_path: Path) -> None:
    """Manifest rows use normalized routing fields from scaffold metadata."""
    from scripts.publish_phase5_scenarios import publish_all

    scaffold = _make_fake_scaffold(tmp_path, n_bases=1)
    base = scaffold / "CELL-0" / "task0"
    (base / "scenario.json").write_text(json.dumps({
        "scenario_id": "CELL-0__t0",
        "agents": [{"agent_id": "a1"}],
    }))
    (base / "phase5_metadata.json").write_text(json.dumps({
        "base_scenario_id": "CD-A-marble_research__t1",
        "cell": {
            "category": "CD",
            "cell_id": "CD-A-marble_research",
            "family_id": "marble_research",
            "slot": "A",
        },
        "task_variant": {
            "task_index": 1,
            "task_label": "alpha_beta_gamma_delta_PROP-12",
        },
        "tier": {
            "tier_index": None,
            "tier_name": None,
        },
    }))
    store = tmp_path / "store"
    client = _FakeNaturalizationClient()

    publish_all(scaffold_dir=scaffold, store_dir=store, client=client,
                naturalization_model="test-model")

    manifest = json.loads((store / "manifest.json").read_text())
    row = manifest["rows"][0]
    assert row["cell_id"] == "CD-A-marble_research"
    assert row["family_id"] == "marble_research"
    assert row["task_index"] == 1
    assert row["tier_index"] is None
    assert row["bundle_dir"] == "research/CELL-0__t0"


def test_publish_with_base_id_filter_preserves_existing_manifest_rows(
    tmp_path: Path,
) -> None:
    """Incremental --base-id publish keeps prior store entries in the manifest.

    Regression test for the manifest-overwrite bug: a per-scenario publish
    used to drop every row except the one just published, requiring a
    manual rebuild via /tmp/patch_manifest.py. The publish script must
    now discover all previously-published bases under store_dir and
    include them alongside the newly-published one.
    """
    from scripts.publish_phase5_scenarios import publish_all

    scaffold = _make_fake_scaffold(tmp_path, n_bases=3)
    store = tmp_path / "store"
    client = _FakeNaturalizationClient()

    publish_all(scaffold_dir=scaffold, store_dir=store, client=client,
                naturalization_model="test-model", base_id_filter="CELL-0__t0")
    publish_all(scaffold_dir=scaffold, store_dir=store, client=client,
                naturalization_model="test-model", base_id_filter="CELL-1__t0")

    manifest = json.loads((store / "manifest.json").read_text())
    base_ids = sorted({r["base_id"] for r in manifest["rows"]})
    assert base_ids == ["CELL-0__t0", "CELL-1__t0"], (
        "manifest should contain rows for both previously-published bases, "
        f"not just the last publish target. got: {base_ids}"
    )
    assert manifest["n_bases"] == 2
    assert manifest["n_variants"] == 10
