"""Reset Phase-5 scaffold resource state and capture initial snapshots.

The Phase-5 family-pack tool handlers mutate per-user sqlite databases
under ``<scaffold>/resources/`` (proposals, orders, reservations,
lines, meetings, items). Those databases are created with
``CREATE TABLE IF NOT EXISTS`` and never truncated by the runtime,
so each rerun appends on top of the prior run's mutations. The
result is that ``get_proposal_status`` returns confused observations
filled with hallucinated result_ids from earlier runs, and the
canonical task becomes untestable.

This script restores each scaffold dir to its seed state by
re-running each family pack's resource materializer, then captures a
``resources_initial/`` snapshot the runtime can restore from on
every subsequent run. Run once after substrate changes that affect
seeded resources; safe to re-run.

Usage::

    python scripts/freshen_phase5_scaffolds.py \\
        --scaffold-root benchmark/phase5/scaffold

Pass ``--dry-run`` to list the scaffolds that would be touched
without writing anything. Pass ``--families marble_research`` to
limit the scope to one pack while iterating on a fix.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent

# Import the family-pack loaders + private resource-writers. We use the
# private ``_write_resources`` rather than the public materializer so
# we don't overwrite the naturalized ``scenario.json`` or the other
# (deterministic) outputs the materializer also emits.
from clawsocialarena.generator.family_packs.marble_research import (  # noqa: E402
    loader as marble_research_loader,
    materialize as marble_research_materialize,
)
from clawsocialarena.generator.family_packs.marble_bargaining import (  # noqa: E402
    loader as marble_bargaining_loader,
    materialize as marble_bargaining_materialize,
)
from clawsocialarena.generator.family_packs.tau2_airline import (  # noqa: E402
    loader as tau2_airline_loader,
    materialize as tau2_airline_materialize,
)
from clawsocialarena.generator.family_packs.tau2_retail import (  # noqa: E402
    loader as tau2_retail_loader,
    materialize as tau2_retail_materialize,
)
from clawsocialarena.generator.family_packs.tau2_telecom import (  # noqa: E402
    loader as tau2_telecom_loader,
    materialize as tau2_telecom_materialize,
)
from clawsocialarena.generator.family_packs.wildclaw_social import (  # noqa: E402
    loader as wildclaw_social_loader,
    materialize as wildclaw_social_materialize,
)


# Shared singletons for the tau2 loader instances. The materializers
# require a ``tau2_loader`` keyword argument that holds the parsed
# upstream tau2-bench data; we construct one per family and reuse it
# across the per-scaffold regen calls.
_TAU2_AIRLINE_LOADER = tau2_airline_loader.Tau2AirlineLoader()
_TAU2_RETAIL_LOADER = tau2_retail_loader.Tau2RetailLoader()
_TAU2_TELECOM_LOADER = tau2_telecom_loader.Tau2TelecomLoader()


def _write_marble_research(bundle: Any, out_dir: Path) -> None:
    marble_research_materialize._write_resources(bundle, out_dir)


def _write_marble_bargaining(bundle: Any, out_dir: Path) -> None:
    marble_bargaining_materialize._write_resources(bundle, out_dir)


def _write_tau2_airline(bundle: Any, out_dir: Path) -> None:
    tau2_airline_materialize._write_resources(
        bundle, out_dir, tau2_loader=_TAU2_AIRLINE_LOADER
    )


def _write_tau2_retail(bundle: Any, out_dir: Path) -> None:
    tau2_retail_materialize._write_resources(
        bundle, out_dir, tau2_loader=_TAU2_RETAIL_LOADER
    )


def _write_tau2_telecom(bundle: Any, out_dir: Path) -> None:
    tau2_telecom_materialize._write_resources(bundle, out_dir)


def _write_wildclaw_social(bundle: Any, out_dir: Path) -> None:
    wildclaw_social_materialize._write_resources(bundle, out_dir)


_FAMILY_REGEN: dict[str, tuple[Callable[..., Any], Callable[..., None]]] = {
    "marble_research": (
        marble_research_loader.load_research_collaboration_scenario,
        _write_marble_research,
    ),
    "marble_bargaining": (
        marble_bargaining_loader.load_bargaining_scenario,
        _write_marble_bargaining,
    ),
    "tau2_airline": (
        tau2_airline_loader.load_group_seat_change_scenario,
        _write_tau2_airline,
    ),
    "tau2_retail": (
        tau2_retail_loader.load_household_exchange_scenario,
        _write_tau2_retail,
    ),
    "tau2_telecom": (
        tau2_telecom_loader.load_family_plan_roaming_scenario,
        _write_tau2_telecom,
    ),
    "wildclaw_social": (
        wildclaw_social_loader.load_meeting_negotiation_scenario,
        _write_wildclaw_social,
    ),
}


def iter_scaffold_dirs(scaffold_root: Path) -> list[Path]:
    """Find every variant dir under ``scaffold_root`` that has a
    ``phase5_metadata.json``. Walks the canonical layout
    ``<cell>/task<i>/tier<j>/`` plus ``attack_variants/<mode>/``.
    """
    out: list[Path] = []
    for metadata in scaffold_root.glob("**/phase5_metadata.json"):
        out.append(metadata.parent)
    return sorted(out)


def freshen_one(
    variant_dir: Path,
    *,
    family_filter: set[str] | None = None,
    dry_run: bool = False,
) -> str:
    """Regenerate ``variant_dir/resources/`` from the family pack
    loader and capture ``resources_initial/``.

    Returns a one-line status string. Does not raise on individual
    failures; the caller logs and continues.
    """
    metadata_path = variant_dir / "phase5_metadata.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return f"SKIP {variant_dir}: cannot read phase5_metadata.json ({exc})"
    family_id = metadata.get("cell", {}).get("family_id") or ""
    if family_filter and family_id not in family_filter:
        return f"SKIP {variant_dir}: family_id={family_id!r} not in filter"
    if family_id not in _FAMILY_REGEN:
        return f"SKIP {variant_dir}: unknown family_id={family_id!r}"
    loader_fn, write_resources_fn = _FAMILY_REGEN[family_id]
    loader_kwargs = metadata.get("task_variant", {}).get("loader_kwargs") or {}
    if dry_run:
        return f"DRY  {variant_dir}: would regen via {family_id} loader"
    try:
        bundle = loader_fn(**loader_kwargs)
    except Exception as exc:  # noqa: BLE001
        return (
            f"FAIL {variant_dir}: loader {family_id} raised "
            f"{type(exc).__name__}: {exc}"
        )
    try:
        write_resources_fn(bundle, variant_dir)
    except Exception as exc:  # noqa: BLE001
        return (
            f"FAIL {variant_dir}: write_resources {family_id} raised "
            f"{type(exc).__name__}: {exc}"
        )
    # Snapshot resources/ -> resources_initial/.
    source = variant_dir / "resources"
    snapshot = variant_dir / "resources_initial"
    if not source.is_dir():
        return f"WARN {variant_dir}: regen produced no resources/ dir"
    if snapshot.exists():
        shutil.rmtree(snapshot)
    shutil.copytree(source, snapshot)
    return f"OK   {variant_dir} ({family_id})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scaffold-root",
        type=Path,
        default=REPO_ROOT / "benchmark" / "phase5" / "scaffold",
        help="Phase-5 scaffold root directory.",
    )
    parser.add_argument(
        "--families",
        nargs="*",
        default=None,
        help=(
            "Optional list of family_ids to freshen. Default: all six. "
            "Useful for iterating on a single pack during development."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the scaffolds that would be touched, but write nothing.",
    )
    args = parser.parse_args()

    family_filter = set(args.families) if args.families else None
    variant_dirs = iter_scaffold_dirs(args.scaffold_root)
    if not variant_dirs:
        print(f"no scaffolds found under {args.scaffold_root}", file=sys.stderr)
        return 2

    print(f"Found {len(variant_dirs)} scaffold variant dirs.")
    ok = 0
    fail = 0
    skip = 0
    for variant_dir in variant_dirs:
        status = freshen_one(
            variant_dir,
            family_filter=family_filter,
            dry_run=args.dry_run,
        )
        prefix = status.split(maxsplit=1)[0]
        if prefix == "OK":
            ok += 1
        elif prefix in {"SKIP", "DRY"}:
            skip += 1
            print(status)
        else:
            fail += 1
            print(status)
    print()
    print(f"summary: {ok} regenerated, {skip} skipped, {fail} failed.")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
