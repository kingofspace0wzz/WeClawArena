"""Append 120 tau2_retail rows (24 bases x 5 attack modes) to the v2.0.0 manifest.

The four archetypes (shared_account, cross_account, store_rep_dyad,
hub_aggregator) each have 6 base scenarios materialized under
``benchmark/scenarios/v2.0.0/retail/<archetype>__t{0..5}/``. This
script registers them as 120 manifest rows so the standard batch
runners (bargaining-style stress calibration, naturalize_and_run_batch)
can pick them up by ``family_id == "tau2_retail"`` and attack-mode
filter.

Row shape mirrors the marble_bargaining rows already in the manifest.
``cell_id`` is synthesized as ``tau2_retail__<archetype>`` since the
archetype is the meaningful grouping axis (the legacy AM-A and CU-B
cells are 3-task household scaffolds that pre-date this design).

Idempotent: if any retail row is already present, the script reports
and exits without writing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "benchmark/scenarios/v2.0.0/manifest.json"
ARCHETYPES = ("shared_account", "cross_account", "store_rep_dyad", "hub_aggregator")
ATTACK_MODES = ("no_attacker", "collaboration", "security", "privacy", "governance")
TASKS_PER_ARCHETYPE = 6


def build_retail_rows() -> list[dict]:
    rows: list[dict] = []
    for archetype in ARCHETYPES:
        for task_index in range(TASKS_PER_ARCHETYPE):
            base_id = f"{archetype}__t{task_index}"
            for attack_mode in ATTACK_MODES:
                rows.append({
                    "attack_mode": attack_mode,
                    "base_id": base_id,
                    "base_scenario_id": base_id,
                    "bundle_dir": f"retail/{base_id}",
                    "cell_id": f"tau2_retail__{archetype}",
                    "family_id": "tau2_retail",
                    "stratum": "main",
                    "task_index": task_index,
                    "tier_index": None,
                    "variant_id": f"{base_id}__{attack_mode}",
                })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    existing_rows = data.get("rows", [])
    existing_retail = [r for r in existing_rows if r.get("family_id") == "tau2_retail"]
    if existing_retail:
        print(f"Manifest already has {len(existing_retail)} tau2_retail rows; nothing to do.")
        return

    retail_rows = build_retail_rows()
    print(f"Appending {len(retail_rows)} tau2_retail rows ({len(ARCHETYPES)} archetypes x {TASKS_PER_ARCHETYPE} tasks x {len(ATTACK_MODES)} modes).")

    if args.dry_run:
        for row in retail_rows[:3]:
            print(json.dumps(row, indent=2))
        print(f"... ({len(retail_rows) - 3} more rows omitted)")
        print("Dry run: not writing.")
        return

    data["rows"] = existing_rows + retail_rows
    data["n_bases"] = data.get("n_bases", 0) + len(ARCHETYPES) * TASKS_PER_ARCHETYPE
    data["n_variants"] = data.get("n_variants", 0) + len(retail_rows)

    args.manifest.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Manifest updated: {args.manifest}")
    print(f"  rows: {len(existing_rows)} -> {len(data['rows'])}")
    print(f"  n_bases: {data['n_bases']}")
    print(f"  n_variants: {data['n_variants']}")


if __name__ == "__main__":
    main()
