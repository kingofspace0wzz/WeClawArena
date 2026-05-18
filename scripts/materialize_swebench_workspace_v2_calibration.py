"""Materialize a small v2 calibration store for swebench_workspace."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from clawsocialarena.generator.family_packs.swebench_workspace import (  # noqa: E402
    load_workspace_coding_scenario,
    materialize_workspace_coding_bundle,
)
from clawsocialarena.generator.family_packs.swebench_workspace.seed_data import (  # noqa: E402
    WORKSPACE_TASK_SEEDS,
)
from clawsocialarena.generator.phase5_store_layout import (  # noqa: E402
    bundle_relative_path_for_base,
)
from scripts.publish_phase5_scenarios import (  # noqa: E402
    ATTACK_MODES,
    _manifest_metadata_for_base,
)


_CALIBRATION_FAMILY_ID = "swebench_workspace"
_CALIBRATION_SUBSTRATE_VERSION = "v2"


def materialize_calibration_store(
    *,
    out_dir: Path,
    limit: int = 6,
    force: bool = False,
) -> dict[str, Any]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    if out_dir.exists():
        if not force:
            raise FileExistsError(f"{out_dir} already exists; pass --force to replace it")
        if not _is_prior_calibration_store(out_dir):
            raise FileExistsError(
                f"{out_dir} is not a swebench_workspace v2 calibration store"
            )
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    selected = WORKSPACE_TASK_SEEDS[:limit]
    rows: list[dict[str, Any]] = []
    for seed in selected:
        bundle = load_workspace_coding_scenario(
            workspace_substrate_version="v2",
            **seed.loader_kwargs(),
        )
        base_id = bundle.scenario.scenario_id
        bundle_rel = bundle_relative_path_for_base(
            base_id,
            family_id=_CALIBRATION_FAMILY_ID,
        )
        bundle_dir = materialize_workspace_coding_bundle(bundle, out_dir / bundle_rel)
        metadata = _manifest_metadata_for_base(bundle_dir, base_id=base_id)
        for mode in ATTACK_MODES:
            rows.append(
                {
                    "variant_id": f"{base_id}__{mode}",
                    "base_id": base_id,
                    "base_scenario_id": base_id,
                    "attack_mode": mode,
                    "bundle_dir": bundle_rel.as_posix(),
                    "stratum": "main",
                    **metadata,
                }
            )

    rows.sort(key=lambda row: str(row["variant_id"]))
    manifest = {
        "version": out_dir.name,
        "n_bases": len(selected),
        "n_modes": len(ATTACK_MODES),
        "n_variants": len(rows),
        "naturalization_model": "none",
        "workspace_substrate_version": _CALIBRATION_SUBSTRATE_VERSION,
        "rows": rows,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--limit", default=6, type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    manifest = materialize_calibration_store(
        out_dir=args.out_dir,
        limit=args.limit,
        force=args.force,
    )
    print(
        json.dumps(
            {
                "out_dir": str(args.out_dir),
                "n_bases": manifest["n_bases"],
                "n_variants": manifest["n_variants"],
            },
            indent=2,
        )
    )
    return 0


def _is_prior_calibration_store(path: Path) -> bool:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(manifest, dict):
        return False
    if manifest.get("workspace_substrate_version") != _CALIBRATION_SUBSTRATE_VERSION:
        return False
    if manifest.get("naturalization_model") != "none":
        return False
    if manifest.get("n_modes") != len(ATTACK_MODES):
        return False
    rows = manifest.get("rows")
    if not isinstance(rows, list) or not rows:
        return False
    if manifest.get("n_variants") != len(rows):
        return False
    for row in rows:
        if not isinstance(row, dict):
            return False
        if row.get("family_id") != _CALIBRATION_FAMILY_ID:
            return False
        bundle_dir = row.get("bundle_dir")
        if not isinstance(bundle_dir, str):
            return False
        if not bundle_dir.startswith(f"{_CALIBRATION_FAMILY_ID}/"):
            return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
