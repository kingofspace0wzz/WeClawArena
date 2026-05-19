"""Materialize claw_clinical and claw_trading base scenarios to the v2.0.0 store.

Usage:
    python scripts/materialize_clinical_trading.py

Writes to benchmark/scenarios/v2.0.0/clinical/ and benchmark/scenarios/v2.0.0/trading/.
Updates benchmark/scenarios/v2.0.0/manifest.json with new rows.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

# ---------------------------------------------------------------------------
# Clinical domain
# ---------------------------------------------------------------------------
from clawsocialarena.generator.family_packs.claw_clinical.loader import (
    load_referral_scenario,
)
from clawsocialarena.generator.family_packs.claw_clinical.materialize import (
    materialize_clinical_bundle,
)

# ---------------------------------------------------------------------------
# Trading domain
# ---------------------------------------------------------------------------
from clawsocialarena.generator.family_packs.claw_trading.loader import (
    load_trading_club_scenario,
)
from clawsocialarena.generator.family_packs.claw_trading.materialize import (
    materialize_trading_bundle,
)


STORE_ROOT = Path("benchmark/scenarios/v2.0.0")
MANIFEST_PATH = STORE_ROOT / "manifest.json"

# Cell assignments from cell_allocation.py
CLINICAL_CELLS = [
    {"cell_index": 18, "category": "HS", "slot": "C", "cell_id": "HS-C-claw_clinical"},
    {"cell_index": 19, "category": "CM", "slot": "D", "cell_id": "CM-D-claw_clinical"},
]

TRADING_CELLS = [
    {"cell_index": 20, "category": "MG", "slot": "D", "cell_id": "MG-D-claw_trading"},
    {"cell_index": 21, "category": "CU", "slot": "E", "cell_id": "CU-E-claw_trading"},
]

# Seed configurations for each domain
CLINICAL_SEEDS = [
    {"case_key": "referral_ent_001", "label": "ent_referral"},
    {"case_key": "referral_cardio_002", "label": "cardio_referral"},
    {"case_key": "emergency_004", "label": "emergency"},
    {"case_key": "discharge_003", "label": "hip_discharge"},
    {"case_key": "discharge_planning_002", "label": "bipolar_discharge"},
]

TRADING_SEEDS = [
    {"case_key": "earnings_debate_001", "label": "earnings_debate"},
    {"case_key": "sector_rotation_003", "label": "sector_rotation"},
    {"case_key": "new_member_004", "label": "new_member"},
    {"case_key": "crisis_response_002", "label": "crisis_response"},
]

ATTACK_MODES = ["no_attacker", "collaboration", "security", "privacy", "governance"]


def _write_phase5_metadata(
    bundle_dir: Path,
    base_id: str,
    cell: dict,
    task_index: int,
    loader_kwargs: dict,
    task_label: str,
) -> None:
    metadata = {
        "base_scenario_id": base_id,
        "cell": {
            "category": cell["category"],
            "cell_id": cell["cell_id"],
            "cell_index": cell["cell_index"],
            "family_id": "claw_clinical" if "clinical" in cell["cell_id"] else "claw_trading",
            "slot": cell["slot"],
        },
        "phase5_version": 1,
        "task_variant": {
            "loader_kwargs": loader_kwargs,
            "task_index": task_index,
            "task_label": task_label,
        },
        "tier": {
            "attack_intensity": 0.4,
            "per_pack_extras": {},
            "scenario_overrides": {"max_turns": 30},
            "tier_index": None,
            "tier_name": None,
        },
    }
    (bundle_dir / "phase5_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n"
    )


def materialize_domain(
    domain: str,
    cells: list[dict],
    seeds: list[dict],
    store_subdir: str,
) -> list[dict]:
    """Materialize all seeds across all cells for a domain. Returns manifest rows."""
    domain_dir = STORE_ROOT / store_subdir
    domain_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    task_index = 0

    for cell in cells:
        for seed in seeds:
            base_id = f"{cell['cell_id']}__{f't{task_index}'}"
            bundle_dir = domain_dir / base_id

            # Skip if already materialized
            if bundle_dir.exists():
                print(f"  [skip] {base_id} (already exists)")
            else:
                scenario_id = f"{domain}_{seed['label']}_{base_id}"
                loader_kwargs = {
                    "scenario_id": scenario_id,
                    "case_key": seed["case_key"],
                }

                try:
                    if domain == "claw_clinical":
                        bundle = load_referral_scenario(**loader_kwargs)
                        materialize_clinical_bundle(bundle, bundle_dir)
                    else:
                        bundle = load_trading_club_scenario(**loader_kwargs)
                        materialize_trading_bundle(bundle, bundle_dir)

                    _write_phase5_metadata(
                        bundle_dir=bundle_dir,
                        base_id=base_id,
                        cell=cell,
                        task_index=task_index,
                        loader_kwargs=loader_kwargs,
                        task_label=f"{seed['label']}_{cell['cell_id']}",
                    )
                    print(f"  [ok]   {base_id}")
                except Exception as e:
                    print(f"  [FAIL] {base_id}: {e}")
                    if bundle_dir.exists():
                        shutil.rmtree(bundle_dir)
                    continue

            family_id = f"claw_{domain.split('_')[-1]}" if "claw_" not in domain else domain

            for mode in ATTACK_MODES:
                variant_id = f"{base_id}__{mode}"
                manifest_rows.append({
                    "attack_mode": mode,
                    "base_id": base_id,
                    "base_scenario_id": base_id,
                    "bundle_dir": f"{store_subdir}/{base_id}",
                    "cell_id": cell["cell_id"],
                    "family_id": family_id,
                    "stratum": "main",
                    "task_index": task_index,
                    "tier_index": None,
                    "variant_id": variant_id,
                })

            task_index += 1

    return manifest_rows


def main() -> None:
    print("Materializing claw_clinical scenarios...")
    clinical_rows = materialize_domain(
        "claw_clinical", CLINICAL_CELLS, CLINICAL_SEEDS, "clinical"
    )
    print(f"  {len(clinical_rows)} manifest rows ({len(clinical_rows)//5} bases x 5 modes)")

    print("\nMaterializing claw_trading scenarios...")
    trading_rows = materialize_domain(
        "claw_trading", TRADING_CELLS, TRADING_SEEDS, "trading"
    )
    print(f"  {len(trading_rows)} manifest rows ({len(trading_rows)//5} bases x 5 modes)")

    # Update manifest
    print("\nUpdating manifest.json...")
    manifest = json.loads(MANIFEST_PATH.read_text())
    existing_families = {r["family_id"] for r in manifest["rows"]}
    new_rows = []
    for row in clinical_rows + trading_rows:
        if row["family_id"] not in existing_families or True:
            new_rows.append(row)

    # Remove any existing clinical/trading rows before adding
    manifest["rows"] = [
        r for r in manifest["rows"]
        if r["family_id"] not in ("claw_clinical", "claw_trading")
    ]
    manifest["rows"].extend(new_rows)
    manifest["rows"].sort(key=lambda r: (r["family_id"], r["base_id"], r["attack_mode"]))

    # Update counts
    bases = {r["base_id"] for r in manifest["rows"]}
    manifest["n_bases"] = len(bases)
    manifest["n_variants"] = len(manifest["rows"])

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"  Total: {manifest['n_bases']} bases, {manifest['n_variants']} variants")
    print("\nDone.")


if __name__ == "__main__":
    main()
