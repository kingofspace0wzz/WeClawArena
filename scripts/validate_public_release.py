#!/usr/bin/env python3
"""Validate the WeClawArena v2.0.0 public release contract."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any


VERSION = "2.0.0"
SCENARIO_ROOT = Path("benchmark/scenarios/v2.0.0")
DOMAIN_BASE_COUNTS = {
    "bargaining": 24,
    "bidding": 12,
    "travel": 20,
    "swebench_workspace": 50,
    "clinical": 10,
    "trading": 8,
}
DOMAIN_FAMILIES = {
    "bargaining": "marble_bargaining",
    "bidding": "marble_bidding",
    "travel": "travel",
    "swebench_workspace": "swebench_workspace",
    "clinical": "claw_clinical",
    "trading": "claw_trading",
}
ATTACK_MODES = {
    "no_attacker",
    "collaboration",
    "governance",
    "privacy",
    "security",
}
REQUIRED_BUNDLE_FILES = {
    "scenario.json",
    "scenario.gt.json",
    "family_pack_context.json",
    "docker-compose.yml",
}
REQUIRED_BUNDLE_DIRS = {"personas", "mcp", "resources"}
REQUIRED_RELEASE_FILES = {
    "README.md",
    "LICENSE",
    "DATASET_LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "CITATION.cff",
    "docs/benchmark_dataset_guide.md",
    "docs/DOCUMENTATION_INDEX.md",
    "docs/huggingface_dataset_card.md",
    "docs/assets/readme/weclawarena-open.png",
    "docs/assets/readme/weclawarena-overview.png",
    "docs/assets/readme/weclawarena-benchmark.png",
    "docs/assets/readme/weclawarena-results.png",
}
FORBIDDEN_TRACKED_EXACT = {
    "AGENTS.md",
    "AGENTS.local.md",
    "CLAUDE.md",
    "docs/design.md",
    "docs/plan.md",
    "docs/preregistration.md",
    "docs/project_status.md",
    "opus47.weclaw_opus47_no_attacker.json",
    "scripts/extend_v2_manifest_with_retail.py",
    "scripts/make_repro_bundle.py",
    "scripts/materialize_tau2_retail_scenarios.py",
    "scripts/phase5_recoverability_debug.py",
    "scripts/run_tau2_retail_gateway_smoke.py",
    "scripts/run_tau2_retail_live_smoke.py",
    "scripts/run_tau2_retail_session_smoke.py",
    "scripts/run_tau2_retail_stress_calibration.py",
    "tests/test_scripts/test_make_repro_bundle.py",
}
FORBIDDEN_TRACKED_PREFIXES = (
    "agents/",
    "benchmark/phase5/",
    "benchmark/scenarios/v1.0.0/",
    "benchmark/scenarios/v2.0.0/retail/",
    "benchmark/scenarios/v2.0.0/research/",
    "docs/archive/",
    "docs/phase5/",
    "docs/phase_5/",
    "docs/reviews/",
    "docs/superpowers/",
    "logs/",
)
PRIVATE_BUNDLE_MARKERS = (
    "benchmark/phase5/pilot/",
    '"pilot_root"',
    '"source_scorecard_path"',
    '"source_transcript_path"',
    '"simulation_usage"',
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _tracked_files(repo_root: Path) -> tuple[set[str], str | None]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        return set(), f"git ls-files failed: {message}"
    return {
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    }, None


def _validate_manifest(repo_root: Path, errors: list[str]) -> None:
    manifest_path = repo_root / SCENARIO_ROOT / "manifest.json"
    if not manifest_path.is_file():
        errors.append(f"missing {manifest_path.relative_to(repo_root)}")
        return

    try:
        manifest = _read_json(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid manifest.json: {exc}")
        return

    rows = manifest.get("rows")
    if not isinstance(rows, list):
        errors.append("manifest rows must be a list")
        return

    expected_bases = sum(DOMAIN_BASE_COUNTS.values())
    expected_variants = expected_bases * len(ATTACK_MODES)
    expected_metadata = {
        "version": f"v{VERSION}",
        "n_bases": expected_bases,
        "n_modes": len(ATTACK_MODES),
        "n_variants": expected_variants,
    }
    for key, expected in expected_metadata.items():
        if manifest.get(key) != expected:
            errors.append(
                f"manifest {key} is {manifest.get(key)!r}; expected {expected!r}"
            )
    if len(rows) != expected_variants:
        errors.append(f"manifest has {len(rows)} rows; expected {expected_variants}")

    rows_by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows_by_base: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    variant_ids: list[str] = []
    checked_bundles: set[Path] = set()

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"manifest row {index} is not an object")
            continue
        bundle_value = row.get("bundle_dir")
        if not isinstance(bundle_value, str):
            errors.append(f"manifest row {index} has no string bundle_dir")
            continue
        bundle_path = PurePosixPath(bundle_value)
        if bundle_path.is_absolute() or ".." in bundle_path.parts:
            errors.append(f"manifest row {index} has unsafe bundle_dir {bundle_value!r}")
            continue
        if len(bundle_path.parts) != 2:
            errors.append(
                f"manifest row {index} bundle_dir must be <domain>/<base_id>: "
                f"{bundle_value!r}"
            )
            continue

        domain, bundle_base = bundle_path.parts
        base_id = row.get("base_id")
        variant_id = row.get("variant_id")
        if domain not in DOMAIN_BASE_COUNTS:
            errors.append(f"manifest row {index} uses excluded domain {domain!r}")
            continue
        if base_id != bundle_base:
            errors.append(
                f"manifest row {index} base_id {base_id!r} does not match "
                f"bundle_dir {bundle_value!r}"
            )
        if row.get("base_scenario_id") != base_id:
            errors.append(f"manifest row {index} base_scenario_id does not match base_id")
        if row.get("family_id") != DOMAIN_FAMILIES[domain]:
            errors.append(
                f"manifest row {index} family_id {row.get('family_id')!r} does not "
                f"match {DOMAIN_FAMILIES[domain]!r}"
            )
        if not isinstance(variant_id, str):
            errors.append(f"manifest row {index} has no string variant_id")
        else:
            variant_ids.append(variant_id)

        rows_by_domain[domain].append(row)
        rows_by_base[(domain, str(base_id))].append(row)

        absolute_bundle = repo_root / SCENARIO_ROOT / Path(*bundle_path.parts)
        if absolute_bundle in checked_bundles:
            continue
        checked_bundles.add(absolute_bundle)
        if not absolute_bundle.is_dir():
            errors.append(f"missing bundle directory {bundle_value}")
            continue
        for filename in sorted(REQUIRED_BUNDLE_FILES):
            if not (absolute_bundle / filename).is_file():
                errors.append(f"{bundle_value} is missing {filename}")
        for dirname in sorted(REQUIRED_BUNDLE_DIRS):
            if not (absolute_bundle / dirname).is_dir():
                errors.append(f"{bundle_value} is missing {dirname}/")
        compose_path = absolute_bundle / "docker-compose.yml"
        if compose_path.is_file():
            compose_text = compose_path.read_text(encoding="utf-8")
            contexts = re.findall(r"^\s+context:\s*([^#\n]+)", compose_text, re.MULTILINE)
            for context in contexts:
                if context.strip().strip("'\"") != "../../../../..":
                    errors.append(
                        f"{bundle_value} has non-portable build context "
                        f"{context.strip()!r}"
                    )

    duplicate_ids = sorted(
        variant_id for variant_id, count in Counter(variant_ids).items() if count > 1
    )
    if duplicate_ids:
        errors.append(f"duplicate variant ids: {', '.join(duplicate_ids[:10])}")

    if set(rows_by_domain) != set(DOMAIN_BASE_COUNTS):
        errors.append(
            "manifest domain set is "
            f"{sorted(rows_by_domain)}; expected {sorted(DOMAIN_BASE_COUNTS)}"
        )
    for domain, expected_bases_for_domain in DOMAIN_BASE_COUNTS.items():
        domain_rows = rows_by_domain.get(domain, [])
        bases = {str(row.get("base_id")) for row in domain_rows}
        expected_rows = expected_bases_for_domain * len(ATTACK_MODES)
        if len(bases) != expected_bases_for_domain:
            errors.append(
                f"{domain} has {len(bases)} bases; expected {expected_bases_for_domain}"
            )
        if len(domain_rows) != expected_rows:
            errors.append(f"{domain} has {len(domain_rows)} rows; expected {expected_rows}")

    for (domain, base_id), base_rows in sorted(rows_by_base.items()):
        modes = {str(row.get("attack_mode")) for row in base_rows}
        if modes != ATTACK_MODES:
            errors.append(
                f"{domain}/{base_id} modes are {sorted(modes)}; "
                f"expected {sorted(ATTACK_MODES)}"
            )


def _validate_private_markers(repo_root: Path, errors: list[str]) -> None:
    for domain in DOMAIN_BASE_COUNTS:
        domain_root = repo_root / SCENARIO_ROOT / domain
        if not domain_root.is_dir():
            continue
        for path in domain_root.rglob("*"):
            if not path.is_file() or path.suffix not in {".json", ".md", ".yml", ".yaml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for marker in PRIVATE_BUNDLE_MARKERS:
                if marker in text:
                    rel_path = path.relative_to(repo_root)
                    errors.append(f"{rel_path} contains private marker {marker!r}")
                    break


def _validate_tracked_boundary(repo_root: Path, errors: list[str]) -> None:
    tracked, git_error = _tracked_files(repo_root)
    if git_error:
        errors.append(git_error)
        return
    for path in sorted(tracked):
        if path in FORBIDDEN_TRACKED_EXACT or path.startswith(FORBIDDEN_TRACKED_PREFIXES):
            errors.append(f"local-only path is still tracked: {path}")


def _validate_metadata(repo_root: Path, errors: list[str]) -> None:
    for relative in sorted(REQUIRED_RELEASE_FILES):
        if not (repo_root / relative).is_file():
            errors.append(f"missing release file {relative}")

    pyproject_path = repo_root / "pyproject.toml"
    try:
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        package_version = pyproject["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"cannot read package version from pyproject.toml: {exc}")
    else:
        if package_version != VERSION:
            errors.append(
                f"pyproject.toml version is {package_version!r}; expected {VERSION!r}"
            )

    plugin_path = repo_root / "gateway_plugin/package.json"
    try:
        plugin_version = _read_json(plugin_path)["version"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read gateway plugin version: {exc}")
    else:
        if plugin_version != VERSION:
            errors.append(
                f"gateway plugin version is {plugin_version!r}; expected {VERSION!r}"
            )


def _validate_readme_links(repo_root: Path, errors: list[str]) -> None:
    readme_path = repo_root / "README.md"
    if not readme_path.is_file():
        return
    text = readme_path.read_text(encoding="utf-8")
    for raw_target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
        target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        file_target = target.split("#", 1)[0]
        if file_target and not (repo_root / file_target).exists():
            errors.append(f"README link target does not exist: {file_target}")


def validate_public_release(repo_root: Path | str) -> list[str]:
    """Return release-contract errors for ``repo_root``."""
    root = Path(repo_root).resolve()
    errors: list[str] = []
    _validate_manifest(root, errors)
    _validate_private_markers(root, errors)
    _validate_tracked_boundary(root, errors)
    _validate_metadata(root, errors)
    _validate_readme_links(root, errors)
    return errors


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    errors = validate_public_release(repo_root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"public release validation failed with {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("public release validation passed: 6 domains, 124 bases, 620 variants")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
