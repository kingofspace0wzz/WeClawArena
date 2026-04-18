"""Build a reproducibility bundle (.tar.gz) for a released results version.

Usage:

    python scripts/make_repro_bundle.py --version 1.0.0 \
        --out /tmp/clawsocialarena-repro.tar.gz

The tarball carries everything a reviewer needs to re-run the analysis
pipeline against the shipped results:

    benchmark/scenarios/<version>/      (or a placeholder note)
    results/<version>/                  (or a placeholder note)
    pyproject.toml                      (if present)
    uv.lock                             (if present)
    docs/preregistration.md             (or a generated stub)
    docs/superpowers/specs/2026-04-17-clawsocialarena-v2-design.md
    replay.sh                           (one-command reproducer)

``replay.sh`` creates a virtualenv, installs the package, runs the
aggregator -> tables -> figures -> prereg pipeline against the bundled
``results/<version>/`` tree, and writes its outputs alongside.

The script never touches the real filesystem outside ``--out``; the
input tree is always copied read-only.
"""

from __future__ import annotations

import argparse
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_REL = "docs/superpowers/specs/2026-04-17-clawsocialarena-v2-design.md"


@dataclass
class BundleInputs:
    """Normalised view of the inputs the bundler needs to stage.

    Attributes:
        repo_root: Repo root the bundler is reading from.
        version: Results version string (e.g., ``"1.0.0"``).
        scenarios_dir: Directory containing generated scenarios for the
            version, or ``None`` if not on disk. When ``None`` the
            bundle stamps a placeholder note in its place.
        results_dir: Directory containing ``run_scorecard.json`` files,
            or ``None``.
        preregistration: Path to ``docs/preregistration.md``, or
            ``None`` to trigger stub generation.
    """

    repo_root: Path
    version: str
    scenarios_dir: Path | None
    results_dir: Path | None
    preregistration: Path | None


def _collect_inputs(repo_root: Path, version: str) -> BundleInputs:
    """Resolve the per-version input paths with generous fallbacks."""

    def _or_none(p: Path) -> Path | None:
        return p if p.exists() else None

    return BundleInputs(
        repo_root=repo_root,
        version=version,
        scenarios_dir=_or_none(repo_root / "benchmark" / "scenarios" / f"v{version}"),
        results_dir=_or_none(repo_root / "results" / f"v{version}"),
        preregistration=_or_none(repo_root / "docs" / "preregistration.md"),
    )


def _write_placeholder_note(path: Path, kind: str, version: str) -> None:
    """Write a short text note in place of a missing input directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# {kind} placeholder\n\n"
        f"This bundle was built for version v{version} before real {kind} "
        "were materialised.\n\n"
        "Regenerate with the appropriate Phase E / Phase G pipeline "
        "once the data is on disk, then re-run make_repro_bundle.py.\n"
    )


def _write_stub_preregistration(path: Path, version: str) -> None:
    """Generate a minimal preregistration stub when docs/preregistration.md is absent."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"# Pre-registration stub (v{version})",
                "",
                "This is a bundled placeholder. The canonical pre-registration",
                "lives at ``docs/preregistration.md`` in the source repository;",
                "this stub is only emitted when the bundler cannot find the",
                "canonical file on disk.",
                "",
                "## Hypotheses (spec §5.8)",
                "",
                "- H1: SAF dims fail under benign conditions, weakest on τ / φ.",
                "- H2: Enforce < Passive < Baseline on privacy + security.",
                "- H3: Enforce has bounded TSR cost: < 10% avg, < 25% worst-case.",
                "- H4: Vanilla-AA overestimates auditability vs SAF.",
                "- H5: Audit condition matters independently of model.",
                "",
            ]
        )
    )


_REPLAY_SH_TEMPLATE = """#!/usr/bin/env bash
# Reproducibility driver for ClawSocialArena v{version}.
#
# Assumes Python >= 3.11 and ``pip`` are on PATH. Re-runs the analysis
# pipeline against the bundled ``results/v{version}/`` tree and regenerates
# tables, figures, and the pre-registration reconciliation report.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

python -m venv "$ROOT/.venv"
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
pip install --upgrade pip
pip install "$ROOT" "$ROOT[dev]"

OUT="$ROOT/reproduced/v{version}"
mkdir -p "$OUT" "$ROOT/paper/figures"

# Aggregate the bundled results to a single wide CSV.
python -m clawsocialarena.analysis aggregate \\
    --root "$ROOT/results/v{version}" --out "$OUT/long.csv"

# Tables.
python -m clawsocialarena.analysis table --csv "$OUT/long.csv" --kind headline --out "$OUT/headline.md"
python -m clawsocialarena.analysis table --csv "$OUT/long.csv" --kind model --out "$OUT/model.md"
python -m clawsocialarena.analysis table --csv "$OUT/long.csv" --kind rewrite --out "$OUT/rewrite.md"

# Figures (four PDFs to paper/figures/).
python -m clawsocialarena.analysis figures --csv "$OUT/long.csv" --out "$ROOT/paper/figures"

# Pre-registration reconciliation report.
python -m clawsocialarena.analysis prereg --csv "$OUT/long.csv" \\
    --out "$OUT/prereg_reconciliation.md" --version v{version}

echo "Reproduced outputs land under $OUT and $ROOT/paper/figures/"
"""


def _write_replay_sh(path: Path, version: str) -> None:
    path.write_text(_REPLAY_SH_TEMPLATE.format(version=version))
    path.chmod(0o755)


def _stage_bundle(staging: Path, inputs: BundleInputs) -> None:
    """Copy/generate every artefact into ``staging``; ``staging`` must be empty."""

    staging.mkdir(parents=True, exist_ok=True)
    version = inputs.version

    # Scenarios.
    scenarios_out = staging / "benchmark" / "scenarios" / f"v{version}"
    if inputs.scenarios_dir is not None:
        shutil.copytree(inputs.scenarios_dir, scenarios_out)
    else:
        _write_placeholder_note(
            scenarios_out / "PLACEHOLDER.md", "benchmark scenarios", version
        )

    # Results.
    results_out = staging / "results" / f"v{version}"
    if inputs.results_dir is not None:
        shutil.copytree(inputs.results_dir, results_out)
    else:
        _write_placeholder_note(
            results_out / "PLACEHOLDER.md", "scorecards", version
        )

    # pyproject + uv.lock.
    for name in ("pyproject.toml", "uv.lock"):
        src = inputs.repo_root / name
        if src.exists():
            shutil.copy2(src, staging / name)

    # Preregistration doc.
    prereg_out = staging / "docs" / "preregistration.md"
    if inputs.preregistration is not None:
        prereg_out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(inputs.preregistration, prereg_out)
    else:
        _write_stub_preregistration(prereg_out, version)

    # Spec.
    spec_src = inputs.repo_root / SPEC_REL
    spec_out = staging / SPEC_REL
    if spec_src.exists():
        spec_out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(spec_src, spec_out)
    else:
        _write_placeholder_note(spec_out, "spec document", version)

    # replay.sh.
    _write_replay_sh(staging / "replay.sh", version)


def build_bundle(
    *,
    version: str,
    out: Path,
    repo_root: Path | None = None,
) -> Path:
    """Build the reproducibility tarball; returns the final tarball path."""

    repo_root = repo_root or REPO_ROOT
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    inputs = _collect_inputs(repo_root, version)
    with tempfile.TemporaryDirectory() as staging_raw:
        staging = Path(staging_raw) / f"clawsocialarena-repro-v{version}"
        _stage_bundle(staging, inputs)
        with tarfile.open(out, "w:gz") as tar:
            tar.add(staging, arcname=staging.name)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build a ClawSocialArena repro bundle.")
    p.add_argument("--version", required=True, help="Results version, e.g. 1.0.0")
    p.add_argument("--out", type=Path, required=True, help="Output .tar.gz path")
    p.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Override the repo root the bundler reads from.",
    )
    args = p.parse_args(argv)
    path = build_bundle(version=args.version, out=args.out, repo_root=args.repo_root)
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
