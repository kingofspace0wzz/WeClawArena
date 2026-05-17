"""Materialize all tau2_retail v2.0.0 scenarios under benchmark/scenarios/v2.0.0/retail/.

Usage:
    python scripts/materialize_tau2_retail_scenarios.py --archetype shared_account
    python scripts/materialize_tau2_retail_scenarios.py --archetype all
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO_ROOT / "benchmark" / "scenarios" / "v2.0.0" / "retail"

ARCHETYPES = ("shared_account", "cross_account", "store_rep_dyad", "hub_aggregator")


def materialize_shared_account() -> None:
    from clawsocialarena.generator.family_packs.tau2_retail import (
        load_shared_account_scenario,
        materialize_shared_account_bundle,
    )
    for task_index in range(6):
        out_dir = OUT_ROOT / f"shared_account__t{task_index}"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        bundle = load_shared_account_scenario(task_index=task_index)
        materialize_shared_account_bundle(bundle, out_dir)
        print(f"materialized {out_dir.relative_to(REPO_ROOT)}")


def materialize_cross_account() -> None:
    from clawsocialarena.generator.family_packs.tau2_retail import (
        load_cross_account_scenario,
        materialize_cross_account_bundle,
    )
    for task_index in range(6):
        out_dir = OUT_ROOT / f"cross_account__t{task_index}"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        bundle = load_cross_account_scenario(task_index=task_index)
        materialize_cross_account_bundle(bundle, out_dir)
        print(f"materialized {out_dir.relative_to(REPO_ROOT)}")


def materialize_store_rep_dyad() -> None:
    from clawsocialarena.generator.family_packs.tau2_retail import (
        load_store_rep_dyad_scenario,
        materialize_store_rep_dyad_bundle,
    )
    for task_index in range(6):
        out_dir = OUT_ROOT / f"store_rep_dyad__t{task_index}"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        bundle = load_store_rep_dyad_scenario(task_index=task_index)
        materialize_store_rep_dyad_bundle(bundle, out_dir)
        print(f"materialized {out_dir.relative_to(REPO_ROOT)}")


def materialize_hub_aggregator() -> None:
    from clawsocialarena.generator.family_packs.tau2_retail import (
        load_hub_aggregator_scenario,
        materialize_hub_aggregator_bundle,
    )
    for task_index in range(6):
        out_dir = OUT_ROOT / f"hub_aggregator__t{task_index}"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        bundle = load_hub_aggregator_scenario(task_index=task_index)
        materialize_hub_aggregator_bundle(bundle, out_dir)
        print(f"materialized {out_dir.relative_to(REPO_ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archetype", choices=(*ARCHETYPES, "all"), default="all")
    args = parser.parse_args()

    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    if args.archetype in ("shared_account", "all"):
        materialize_shared_account()
    if args.archetype in ("cross_account", "all"):
        materialize_cross_account()
    if args.archetype in ("store_rep_dyad", "all"):
        materialize_store_rep_dyad()
    if args.archetype in ("hub_aggregator", "all"):
        materialize_hub_aggregator()
    # All 4 archetypes wired.


if __name__ == "__main__":
    main()
