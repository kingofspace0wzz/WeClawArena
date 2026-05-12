"""Drop tier2/ and tier3/ subdirs from an existing phase5 scaffold.

After running this on a pre-v2 scaffold, the layout flattens to
``<cell>/task<N>/`` and the generator's regenerated `phase5_base_index.json`
matches the new 42-base shape.

Usage:
    python scripts/migrate_scaffold_drop_tier.py --scaffold-dir benchmark/phase5/scaffold
    python scripts/migrate_scaffold_drop_tier.py --scaffold-dir benchmark/phase5/scaffold --dry-run
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scaffold-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root: Path = args.scaffold_dir
    if not root.is_dir():
        print(f"error: scaffold dir not found at {root}", file=sys.stderr)
        return 2

    to_remove: list[Path] = []
    to_rename: list[tuple[Path, Path]] = []
    for cell_dir in sorted(root.iterdir()):
        if not cell_dir.is_dir():
            continue
        for task_dir in sorted(cell_dir.glob("task*")):
            if not task_dir.is_dir():
                continue
            # Collect tier2/ and tier3/ subdirs to remove.
            for tier_subdir in ("tier2", "tier3"):
                candidate = task_dir / tier_subdir
                if candidate.is_dir():
                    to_remove.append(candidate)
            # If tier1/ is the only remaining tier, rename its contents
            # one level up so the layout matches <cell>/task<N>/.
            tier1 = task_dir / "tier1"
            if tier1.is_dir():
                to_rename.append((tier1, task_dir))

    print(f"to_remove: {len(to_remove)}")
    for p in to_remove:
        print(f"  rm -rf {p.relative_to(root)}")
    print(f"to_rename: {len(to_rename)}")
    for src, dst in to_rename:
        print(f"  mv {src.relative_to(root)}/* {dst.relative_to(root)}/")

    if args.dry_run:
        print("dry-run: no changes applied")
        return 0

    for path in to_remove:
        shutil.rmtree(path)
    for src, dst in to_rename:
        for child in src.iterdir():
            target = dst / child.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            shutil.move(str(child), str(target))
        src.rmdir()

    print(f"migration applied: removed {len(to_remove)} tier subdirs, "
          f"flattened {len(to_rename)} task dirs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
