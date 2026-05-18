"""Path helpers for the published Phase-5 scenario store.

Scenario IDs remain flat and stable, e.g. ``CD-A-marble_research__t0``.
The v2.0.0 store groups the physical bundles by task domain:

    benchmark/scenarios/v2.0.0/research/CD-A-marble_research__t0/

The helpers here keep that layout out of publisher/runtime call sites and
preserve compatibility with older flat stores during transition.
"""
from __future__ import annotations

import re
from pathlib import Path


_SOURCE_PREFIXES = ("marble_", "tau2_", "wildclaw_")


def task_domain_for_family(family_id: str) -> str:
    """Return the top-level task-domain folder for a family id."""
    family = _sanitize_path_component(family_id)
    for prefix in _SOURCE_PREFIXES:
        if family.startswith(prefix):
            return family[len(prefix):]
    return family


def family_id_from_base_id(base_id: str) -> str:
    """Extract the family id from ``<category>-<slot>-<family>__t<N>``."""
    cell_id = str(base_id).split("__t", 1)[0]
    parts = cell_id.split("-", 2)
    return parts[2] if len(parts) == 3 else cell_id


def bundle_relative_path_for_base(
    base_id: str,
    *,
    family_id: str | None = None,
) -> Path:
    """Return ``<task-domain>/<base_id>`` for a published base bundle."""
    family = family_id or family_id_from_base_id(base_id)
    return Path(task_domain_for_family(family)) / _sanitize_path_component(base_id)


def resolve_store_base_dir(
    *,
    store_dir: Path,
    base_id: str,
    bundle_dir: str | Path | None = None,
) -> Path:
    """Resolve a base bundle in a domain-folder store, with flat fallback.

    ``bundle_dir`` is the manifest-provided relative path when available.
    During migration, old flat stores may still contain ``<store>/<base_id>``;
    this helper accepts both layouts and returns the first existing path.
    """
    candidates: list[Path] = []
    if bundle_dir:
        candidates.append(store_dir / Path(bundle_dir))
    candidates.append(store_dir / bundle_relative_path_for_base(base_id))
    candidates.append(store_dir / _sanitize_path_component(base_id))

    seen: set[Path] = set()
    unique_candidates: list[Path] = []
    for candidate in candidates:
        if candidate not in seen:
            unique_candidates.append(candidate)
            seen.add(candidate)
    for candidate in unique_candidates:
        if candidate.is_dir():
            return candidate
    checked = ", ".join(str(p) for p in unique_candidates)
    raise FileNotFoundError(f"base bundle missing in store: {base_id}; checked {checked}")


def _sanitize_path_component(value: str) -> str:
    out = re.sub(r"[^A-Za-z0-9_.=-]+", "_", str(value).strip())
    return out.strip("._") or "unknown"
