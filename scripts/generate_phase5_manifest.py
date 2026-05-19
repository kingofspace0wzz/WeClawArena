"""CLI driver for the Phase-5 manifest assembler (S3 step 7).

Materializes the 810 main attack variants + 58 supplementary
descriptors into ``out_dir`` and writes ``phase5_manifest.json`` at
the top of that directory. Run-Batch 1..5 orchestrators consume the
manifest by stratum/tier/task to pick rows for each batch.

Example:

    python scripts/generate_phase5_manifest.py \
        --out-dir benchmark/phase5/scaffold

The script is idempotent: re-running it overwrites the manifest and
re-materializes the bundles. For a fresh build, point ``--out-dir``
at an empty directory.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the script runnable from any cwd without requiring PYTHONPATH=. -
# repo root is the parent of the scripts/ directory.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from clawsocialarena.generator.phase5_manifest import (  # noqa: E402
    EXPECTED_MAIN_VARIANTS,
    EXPECTED_SUPPLEMENTARY_VARIANTS,
    EXPECTED_TOTAL_VARIANTS,
    PHASE5_MANIFEST_FILENAME,
    assemble_manifest,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        required=True,
        type=Path,
        help="Directory to materialize bundles + manifest into.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the per-stratum summary print.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = assemble_manifest(out_dir=out_dir)
    if not args.quiet:
        # Brief stratum summary so the orchestrator's log shows the
        # pilot math in one line.
        main_rows = manifest["main"]
        per_tier = {
            tier: sum(1 for r in main_rows if r["tier_index"] == tier)
            for tier in (1, 2, 3)
        }
        per_mode = {
            mode: sum(1 for r in main_rows if r["attack_mode"] == mode)
            for mode in sorted({r["attack_mode"] for r in main_rows})
        }
        print(
            json.dumps(
                {
                    "phase5_manifest": str(out_dir / PHASE5_MANIFEST_FILENAME),
                    "n_main": manifest["n_main"],
                    "n_supplementary": manifest["n_supplementary"],
                    "n_total": manifest["n_total"],
                    "expected_total": EXPECTED_TOTAL_VARIANTS,
                    "main_per_tier": per_tier,
                    "main_per_attack_mode": per_mode,
                },
                indent=2,
            )
        )
    assert manifest["n_main"] == EXPECTED_MAIN_VARIANTS
    assert manifest["n_supplementary"] == EXPECTED_SUPPLEMENTARY_VARIANTS
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
