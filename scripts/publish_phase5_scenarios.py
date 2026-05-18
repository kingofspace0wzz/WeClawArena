"""Publish naturalized scenarios from phase5/scaffold/ to scenarios/v2.0.0/.

Walks the scaffold directory, computes a sha256 hash of each base's
pre-naturalization input, and either skips (cache hit) or calls
the naturalization client (cache miss). Writes the rendered bundle
plus a naturalization_record.json sidecar to the v2 store. Published
bundles are grouped by task domain, e.g. ``research/<base_id>/``.
Finally
emits scenarios/v2.0.0/manifest.json describing all variants
(bases x 5 attack modes).

CLI:
    python scripts/publish_phase5_scenarios.py \\
        --scaffold-dir benchmark/phase5/scaffold \\
        --store-dir benchmark/scenarios/v2.0.0 \\
        --naturalization-model gpt-5.2 \\
        --max-workers 4 \\
        [--base-id <id>] [--force] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from clawsocialarena.generator.phase5_store_layout import (  # noqa: E402
    bundle_relative_path_for_base,
)


ATTACK_MODES = ("no_attacker", "security", "privacy", "governance", "collaboration")


@dataclass
class PublishOutcome:
    base_id: str
    status: str        # "ok" | "skipped" | "failed"
    input_hash: str
    tokens_used: int
    error: str | None = None


class NaturalizationClient(Protocol):
    def naturalize(self, *, base_dir: Path) -> dict[str, Any]: ...


def compute_input_hash(base_dir: Path) -> str:
    """sha256 over canonicalized pre-naturalization inputs.

    Reads scenario.json, scenario.gt.json, family_pack_context.json
    in sorted-keys form and hashes the concatenated UTF-8 bytes.
    """
    h = hashlib.sha256()
    for name in ("scenario.json", "scenario.gt.json", "family_pack_context.json"):
        p = base_dir / name
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            h.update(json.dumps(data, sort_keys=True, separators=(",", ":"))
                     .encode("utf-8"))
            h.update(b"\0")
    return f"sha256:{h.hexdigest()}"


def _read_existing_record(store_base: Path) -> dict[str, Any] | None:
    path = store_base / "naturalization_record.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _publish_one_base(
    *,
    base_dir: Path,
    store_base: Path,
    client: NaturalizationClient,
    naturalization_model: str,
    force: bool,
    dry_run: bool,
) -> PublishOutcome:
    base_id = base_dir.name
    if base_dir.parent.name.startswith("task") or base_dir.name.startswith("task"):
        # Layout: <cell>/task<N>/. base_id := "<cell>__t<N>".
        base_id = f"{base_dir.parent.name}__t{base_dir.name[4:]}"

    input_hash = compute_input_hash(base_dir)
    existing = _read_existing_record(store_base)
    if existing and existing.get("input_hash") == input_hash and not force:
        return PublishOutcome(
            base_id=base_id, status="skipped",
            input_hash=input_hash, tokens_used=0,
        )
    if dry_run:
        return PublishOutcome(
            base_id=base_id, status="dry_run",
            input_hash=input_hash, tokens_used=0,
        )

    if store_base.exists():
        shutil.rmtree(store_base)
    store_base.mkdir(parents=True, exist_ok=True)

    # Copy the pre-naturalization base files into the store.
    for child in base_dir.iterdir():
        dst = store_base / child.name
        if child.is_dir():
            shutil.copytree(child, dst)
        else:
            shutil.copy2(child, dst)

    try:
        patch = client.naturalize(base_dir=store_base)
    except Exception as exc:
        record = {
            "input_hash": input_hash,
            "naturalization_model": naturalization_model,
            "naturalization_run_ts": _dt.datetime.utcnow().isoformat(),
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
        (store_base / "naturalization_record.json").write_text(
            json.dumps(record, indent=2, sort_keys=True), encoding="utf-8"
        )
        return PublishOutcome(
            base_id=base_id, status="failed",
            input_hash=input_hash, tokens_used=0,
            error=record["error"],
        )

    _apply_naturalization_patch(store_base=store_base, patch=patch)
    tokens = patch.get("tokens_used", {}) or {}
    record = {
        "input_hash": input_hash,
        "naturalization_model": naturalization_model,
        "naturalization_run_ts": _dt.datetime.utcnow().isoformat(),
        "naturalization_tokens_used": tokens,
        "naturalization_template_version": "v1",
        "status": "ok",
    }
    (store_base / "naturalization_record.json").write_text(
        json.dumps(record, indent=2, sort_keys=True), encoding="utf-8"
    )
    return PublishOutcome(
        base_id=base_id, status="ok",
        input_hash=input_hash,
        tokens_used=int(tokens.get("prompt", 0)) + int(tokens.get("completion", 0)),
    )


def _apply_naturalization_patch(*, store_base: Path, patch: dict[str, Any]) -> None:
    """Write personas and apply scenario overrides from the naturalization patch."""
    personas = patch.get("personas") or {}
    if personas:
        out = store_base / "personas"
        out.mkdir(parents=True, exist_ok=True)
        for agent_id, persona in personas.items():
            system_path = out / f"{agent_id}.system.md"
            tools_path = out / f"{agent_id}.tools.json"
            existing_system_md = (
                system_path.read_text(encoding="utf-8")
                if system_path.is_file()
                else ""
            )
            system_path.write_text(
                _merge_naturalized_system_md(
                    existing_system_md=existing_system_md,
                    naturalized_system_md=str(persona.get("system_md") or ""),
                ),
                encoding="utf-8",
            )
            tools_json = persona.get("tools_json")
            if _empty_tool_manifest(tools_json) and tools_path.is_file():
                continue
            tools_path.write_text(
                json.dumps(tools_json or {}, indent=2),
                encoding="utf-8",
            )
    overrides = patch.get("rendered_scenario_overrides") or {}
    if overrides:
        scenario_path = store_base / "scenario.json"
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        for key, value in overrides.items():
            # opening_message keeps its existing {from, to, content} envelope
            # when the override is a bare string (the rendered prose). Replacing
            # only `content` preserves routing fields the executor relies on.
            if (
                key == "opening_message"
                and isinstance(scenario.get("opening_message"), dict)
                and isinstance(value, str)
            ):
                scenario["opening_message"] = {
                    **scenario["opening_message"],
                    "content": value,
                }
            else:
                scenario[key] = value
        scenario_path.write_text(
            json.dumps(scenario, indent=2, sort_keys=True), encoding="utf-8"
        )


def _merge_naturalized_system_md(
    *,
    existing_system_md: str,
    naturalized_system_md: str,
) -> str:
    naturalized = naturalized_system_md.strip()
    if "## Runtime Interface" not in existing_system_md:
        return naturalized
    marker = "## Persona prompt"
    prefix = existing_system_md.split(marker, 1)[0].rstrip()
    return f"{prefix}\n\n{marker}\n\n{naturalized}\n"


def _empty_tool_manifest(value: Any) -> bool:
    return value is None or value == {} or value == []


def publish_all(
    *,
    scaffold_dir: Path,
    store_dir: Path,
    client: NaturalizationClient,
    naturalization_model: str,
    max_workers: int = 4,
    base_id_filter: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> list[PublishOutcome]:
    """Walk the scaffold and publish every base. Returns per-base outcomes."""
    bases: list[tuple[str, Path]] = []
    for cell_dir in sorted(scaffold_dir.iterdir()):
        if not cell_dir.is_dir():
            continue
        for task_dir in sorted(cell_dir.glob("task*")):
            if not task_dir.is_dir():
                continue
            base_id = f"{cell_dir.name}__t{task_dir.name[4:]}"
            if base_id_filter and base_id != base_id_filter:
                continue
            bases.append((base_id, task_dir))

    outcomes: list[PublishOutcome | None] = [None] * len(bases)
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as ex:
        futures = {
            ex.submit(
                _publish_one_base,
                base_dir=base_dir,
                store_base=store_dir / _store_relative_path_for_base(
                    base_dir=base_dir,
                    base_id=base_id,
                ),
                client=client,
                naturalization_model=naturalization_model,
                force=force,
                dry_run=dry_run,
            ): idx
            for idx, (base_id, base_dir) in enumerate(bases)
        }
        for fut in as_completed(futures):
            outcomes[futures[fut]] = fut.result()

    # Emit manifest. Source of truth is store_dir on disk, not this run's
    # filter -- otherwise an incremental --base-id publish would drop
    # every row except the one just published. We treat any subdir
    # containing a naturalization_record.json as a published base.
    store_dir.mkdir(parents=True, exist_ok=True)
    published_bases = _discover_published_bases(store_dir)
    rows: list[dict[str, Any]] = []
    for base_id, bundle_dir in published_bases:
        metadata = _manifest_metadata_for_base(store_dir / bundle_dir, base_id=base_id)
        for mode in ATTACK_MODES:
            rows.append({
                "variant_id": f"{base_id}__{mode}",
                "base_id": base_id,
                "base_scenario_id": base_id,
                "attack_mode": mode,
                "bundle_dir": bundle_dir.as_posix(),
                "stratum": "main",
                **metadata,
            })
    rows.sort(key=lambda r: r["variant_id"])
    manifest = {
        "version": store_dir.name,
        "n_bases": len(published_bases),
        "n_modes": len(ATTACK_MODES),
        "n_variants": len(rows),
        "naturalization_model": naturalization_model,
        "rows": rows,
    }
    (store_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    return outcomes


def _store_relative_path_for_base(*, base_dir: Path, base_id: str) -> Path:
    metadata = _manifest_metadata_for_base(base_dir, base_id=base_id)
    family_id = str(metadata.get("family_id") or "")
    return bundle_relative_path_for_base(base_id, family_id=family_id or None)


def _discover_published_bases(store_dir: Path) -> list[tuple[str, Path]]:
    """Return ``[(base_id, bundle_dir)]`` from flat or domain-folder stores."""
    discovered: dict[str, Path] = {}
    for record_path in sorted(store_dir.rglob("naturalization_record.json")):
        base_dir = record_path.parent
        if base_dir == store_dir:
            continue
        rel = base_dir.relative_to(store_dir)
        base_id = base_dir.name
        current = discovered.get(base_id)
        if current is None or len(rel.parts) > len(current.parts):
            discovered[base_id] = rel
    return sorted(discovered.items())


def _manifest_metadata_for_base(base_dir: Path, *, base_id: str) -> dict[str, Any]:
    """Return run-batch routing metadata for a published base bundle."""
    scenario: dict[str, Any] = {}
    phase5_metadata: dict[str, Any] = {}
    scenario_path = base_dir / "scenario.json"
    if scenario_path.is_file():
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    metadata_path = base_dir / "phase5_metadata.json"
    if metadata_path.is_file():
        phase5_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    cell_metadata = phase5_metadata.get("cell")
    if not isinstance(cell_metadata, dict):
        cell_metadata = {}
    tier_metadata = phase5_metadata.get("tier")
    if not isinstance(tier_metadata, dict):
        tier_metadata = {}

    family_id = (
        scenario.get("family_id")
        or phase5_metadata.get("family_id")
        or cell_metadata.get("family_id")
        or phase5_metadata.get("family")
        or scenario.get("task_family")
    )
    cell_id = (
        phase5_metadata.get("cell_id")
        or cell_metadata.get("cell_id")
        or (phase5_metadata.get("cell") if not cell_metadata else None)
        or _cell_id_from_base_id(base_id)
    )
    return {
        "cell_id": str(cell_id) if cell_id is not None else "",
        "family_id": str(family_id) if family_id is not None else "",
        "task_index": _task_index_for_base(base_id, phase5_metadata),
        "tier_index": phase5_metadata.get("tier_index", tier_metadata.get("tier_index")),
    }


def _cell_id_from_base_id(base_id: str) -> str:
    return base_id.split("__t", 1)[0]


def _task_index_for_base(base_id: str, metadata: dict[str, Any]) -> int:
    raw = metadata.get("task_index")
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    variant = metadata.get("task_variant")
    if isinstance(variant, dict):
        raw = variant.get("task_index")
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
    if isinstance(variant, int) and not isinstance(variant, bool):
        return variant
    if isinstance(variant, str):
        match = re.search(r"(\d+)$", variant)
        if match:
            return int(match.group(1))
    match = re.search(r"__t(\d+)$", base_id)
    return int(match.group(1)) if match else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scaffold-dir", type=Path, required=True)
    parser.add_argument("--store-dir", type=Path, required=True)
    parser.add_argument("--naturalization-model", default="gpt-5.2")
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--base-id", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        class _Stub:
            def naturalize(self, *, base_dir: Path) -> dict[str, Any]:
                return {"naturalization_status": "dry_run", "tokens_used": {}}
        client: NaturalizationClient = _Stub()
    else:
        from clawsocialarena.generator.phase5_naturalization import (
            Phase5NaturalizationClient,
        )
        client = Phase5NaturalizationClient(model=args.naturalization_model)

    outcomes = publish_all(
        scaffold_dir=args.scaffold_dir,
        store_dir=args.store_dir,
        client=client,
        naturalization_model=args.naturalization_model,
        max_workers=args.max_workers,
        base_id_filter=args.base_id,
        force=args.force,
        dry_run=args.dry_run,
    )

    n_ok = sum(1 for o in outcomes if o is not None and o.status == "ok")
    n_skipped = sum(1 for o in outcomes if o is not None and o.status == "skipped")
    n_failed = sum(1 for o in outcomes if o is not None and o.status == "failed")
    total_tokens = sum((o.tokens_used for o in outcomes if o is not None), 0)
    print(json.dumps({
        "n_total": len(outcomes),
        "n_ok": n_ok,
        "n_skipped": n_skipped,
        "n_failed": n_failed,
        "total_tokens": total_tokens,
        "failures": [
            {"base_id": o.base_id, "error": o.error}
            for o in outcomes if o is not None and o.status == "failed"
        ],
    }, indent=2))
    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
